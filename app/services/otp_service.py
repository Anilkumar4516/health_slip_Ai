import hmac
import hashlib
import secrets
import datetime
import logging
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from app.config import settings
from app.models.verification import AuthOtp, AuditEvent
from app.services.sms_provider import get_sms_provider

logger = logging.getLogger("healthslip.otp")

class OtpService:
    @staticmethod
    def _hash_otp(otp_code: str, salt: str) -> str:
        """Hash OTP with secret key and random salt using HMAC-SHA256"""
        combined = f"{otp_code}:{salt}".encode("utf-8")
        return hmac.new(settings.SECRET_KEY.encode("utf-8"), combined, hashlib.sha256).hexdigest()

    @staticmethod
    def generate_otp(db: Session, phone_number: str, receipt_number: Optional[str] = None, ip_address: Optional[str] = None) -> Tuple[bool, str, Optional[str], Optional[int]]:
        """
        Generate 6-digit OTP with multi-layered rate limiting:
        1. 60-second cooldown per phone number
        2. Per-phone rate limit (max N requests per hour)
        3. Per-IP rate limit (max M requests per hour)
        4. Pluggable SMS Provider delivery (MSG91 / Fast2SMS / Console Mock)
        5. Absolute suppression of sandbox_otp in production environments
        """
        now = datetime.datetime.utcnow()
        clean_phone = phone_number.strip().replace(" ", "").replace("-", "")
        one_hour_ago = now - datetime.timedelta(hours=1)

        # 1. Per-Phone Rate Limiting Check (Hourly Max)
        phone_requests_count = db.query(AuditEvent).filter(
            AuditEvent.action == "OTP_REQUEST",
            AuditEvent.resource_id == clean_phone,
            AuditEvent.created_at >= one_hour_ago
        ).count()

        if phone_requests_count >= settings.RATE_LIMIT_PHONE_MAX_PER_HOUR:
            db.add(AuditEvent(
                action="OTP_RATE_LIMITED",
                resource_type="auth_otps",
                resource_id=clean_phone,
                ip_address=ip_address,
                payload_after={"reason": "Hourly phone rate limit exceeded", "count": phone_requests_count}
            ))
            db.commit()
            return False, f"Too many OTP requests for this phone number. Please try again after 1 hour.", None, None

        # 2. Per-IP Rate Limiting Check (Hourly Max)
        if ip_address and ip_address not in ("127.0.0.1", "localhost", "testclient"):
            ip_requests_count = db.query(AuditEvent).filter(
                AuditEvent.action == "OTP_REQUEST",
                AuditEvent.ip_address == ip_address,
                AuditEvent.created_at >= one_hour_ago
            ).count()

            if ip_requests_count >= settings.RATE_LIMIT_IP_MAX_PER_HOUR:
                db.add(AuditEvent(
                    action="OTP_RATE_LIMITED",
                    resource_type="auth_otps",
                    resource_id=clean_phone,
                    ip_address=ip_address,
                    payload_after={"reason": "Hourly IP rate limit exceeded", "count": ip_requests_count}
                ))
                db.commit()
                return False, "Too many OTP requests from this network. Please try again after 1 hour.", None, None

        # 3. 60-Second Cooldown Check
        recent_request = db.query(AuthOtp).filter(
            AuthOtp.identifier == clean_phone,
            AuthOtp.created_at >= now - datetime.timedelta(seconds=settings.OTP_COOLDOWN_SECONDS)
        ).first()

        if recent_request:
            remaining_cooldown = int(settings.OTP_COOLDOWN_SECONDS - (now - recent_request.created_at).total_seconds())
            db.add(AuditEvent(
                action="OTP_COOLDOWN_BLOCKED",
                resource_type="auth_otps",
                resource_id=clean_phone,
                ip_address=ip_address,
                payload_after={"status": "BLOCKED", "remaining_cooldown": remaining_cooldown}
            ))
            db.commit()
            return False, f"Please wait {remaining_cooldown} seconds before requesting a new OTP.", None, None

        # Clean unconsumed previous OTPs
        db.query(AuthOtp).filter(
            AuthOtp.identifier == clean_phone,
            AuthOtp.is_consumed == False
        ).delete()

        # Generate 6-digit cryptographically secure OTP
        otp_code = f"{secrets.randbelow(900000) + 100000}"
        salt = secrets.token_hex(8)
        hashed_payload = f"{salt}${OtpService._hash_otp(otp_code, salt)}"
        expires_at = now + datetime.timedelta(minutes=settings.OTP_EXPIRY_MINUTES)

        otp_record = AuthOtp(
            identifier=clean_phone,
            otp_hash=hashed_payload,
            channel="SMS",
            attempt_count=0,
            is_consumed=False,
            expires_at=expires_at
        )
        db.add(otp_record)

        # 4. Deliver via Pluggable SMS Gateway
        sms_provider = get_sms_provider()
        sms_ok, sms_detail = sms_provider.send_otp(clean_phone, otp_code)

        db.add(AuditEvent(
            action="OTP_REQUEST",
            resource_type="auth_otps",
            resource_id=clean_phone,
            ip_address=ip_address,
            payload_after={
                "status": "SENT" if sms_ok else "GATEWAY_FAILED",
                "channel": "SMS",
                "provider": sms_provider.__class__.__name__,
                "sms_detail": sms_detail
            }
        ))
        db.commit()

        expires_in = settings.OTP_EXPIRY_MINUTES * 60

        # Production security: Never leak sandbox OTP in production or when sandbox mode is off
        is_prod = settings.ENVIRONMENT.lower() == "production" or not settings.DEBUG
        sandbox_otp = None if (is_prod or not settings.DEV_OTP_SANDBOX_MODE) else otp_code

        return True, "OTP sent successfully to registered patient mobile.", sandbox_otp, expires_in

    @staticmethod
    def verify_otp(db: Session, phone_number: str, otp_code: str, receipt_number: Optional[str] = None, ip_address: Optional[str] = None) -> Tuple[bool, str, Optional[str]]:
        """
        Verify submitted OTP against salt-hashed record in healthslip_prod.auth_otps.
        Locks out after 3 failed attempts.
        """
        now = datetime.datetime.utcnow()
        clean_phone = phone_number.strip().replace(" ", "").replace("-", "")

        record = db.query(AuthOtp).filter(
            AuthOtp.identifier == clean_phone,
            AuthOtp.is_consumed == False,
            AuthOtp.expires_at > now
        ).order_by(AuthOtp.created_at.desc()).first()

        if not record:
            db.add(AuditEvent(
                action="OTP_VERIFY_FAILED",
                resource_type="auth_otps",
                resource_id=clean_phone,
                ip_address=ip_address,
                payload_after={"status": "FAILED", "reason": "Expired or not found"}
            ))
            db.commit()
            return False, "OTP has expired or does not exist. Please request a new one.", None

        if record.attempt_count >= settings.OTP_MAX_ATTEMPTS:
            db.add(AuditEvent(
                action="OTP_LOCKOUT",
                resource_type="auth_otps",
                resource_id=clean_phone,
                ip_address=ip_address,
                payload_after={"status": "BLOCKED", "reason": "Max attempts exceeded", "attempts": record.attempt_count}
            ))
            db.commit()
            return False, "Maximum verification attempts exceeded. Please request a new OTP.", None

        record.attempt_count += 1
        stored_salt, stored_hash = record.otp_hash.split("$", 1)
        computed_hash = OtpService._hash_otp(otp_code.strip(), stored_salt)

        if not hmac.compare_digest(computed_hash, stored_hash):
            remaining_attempts = max(0, settings.OTP_MAX_ATTEMPTS - record.attempt_count)
            db.add(AuditEvent(
                action="OTP_VERIFY_FAILED",
                resource_type="auth_otps",
                resource_id=clean_phone,
                ip_address=ip_address,
                payload_after={"remaining_attempts": remaining_attempts}
            ))
            db.commit()
            return False, f"Invalid OTP code. {remaining_attempts} attempt(s) remaining.", None

        # Success - consume OTP and generate signed access token
        record.is_consumed = True
        record.consumed_at = now

        access_token_payload = f"{clean_phone}:{secrets.token_hex(16)}:{now.isoformat()}"
        access_token = hmac.new(settings.SECRET_KEY.encode("utf-8"), access_token_payload.encode("utf-8"), hashlib.sha256).hexdigest()

        # Update AuthOtp record with granted token for validation
        record.otp_hash = f"VERIFIED${access_token}"
        record.expires_at = now + datetime.timedelta(hours=24) # Access valid for 24h

        db.add(AuditEvent(
            action="OTP_VERIFY_SUCCESS",
            resource_type="auth_otps",
            resource_id=clean_phone,
            ip_address=ip_address,
            payload_after={"status": "VERIFIED"}
        ))
        db.commit()

        return True, "Patient verified successfully.", access_token

    @staticmethod
    def validate_access_token(db: Session, token: str) -> Optional[AuthOtp]:
        """Validate patient verification token against database"""
        if not token:
            return None

        now = datetime.datetime.utcnow()
        search_hash = f"VERIFIED${token.strip()}"
        record = db.query(AuthOtp).filter(
            AuthOtp.otp_hash == search_hash,
            AuthOtp.is_consumed == True,
            AuthOtp.expires_at > now
        ).first()

        return record
