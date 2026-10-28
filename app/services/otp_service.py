import hmac
import hashlib
import secrets
import datetime
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from app.config import settings
from app.models.verification import AuthOtp, AuditEvent

class OtpService:
    @staticmethod
    def _hash_otp(otp_code: str, salt: str) -> str:
        """Hash OTP with secret key and random salt using HMAC-SHA256"""
        combined = f"{otp_code}:{salt}".encode("utf-8")
        return hmac.new(settings.SECRET_KEY.encode("utf-8"), combined, hashlib.sha256).hexdigest()

    @staticmethod
    def generate_otp(db: Session, phone_number: str, receipt_number: Optional[str] = None, ip_address: Optional[str] = None) -> Tuple[bool, str, Optional[str], Optional[int]]:
        """
        Generate 6-digit OTP with rate limiting & expiration.
        Stores in healthslip_prod auth_otps table.
        """
        now = datetime.datetime.utcnow()
        clean_phone = phone_number.strip().replace(" ", "").replace("-", "")

        # Rate Limiting Check: Check cooldown
        recent_request = db.query(AuthOtp).filter(
            AuthOtp.identifier == clean_phone,
            AuthOtp.created_at >= now - datetime.timedelta(seconds=settings.OTP_COOLDOWN_SECONDS)
        ).first()

        if recent_request:
            remaining_cooldown = int(settings.OTP_COOLDOWN_SECONDS - (now - recent_request.created_at).total_seconds())
            db.add(AuditEvent(
                action="OTP_REQUEST",
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

        db.add(AuditEvent(
            action="OTP_REQUEST",
            resource_type="auth_otps",
            resource_id=clean_phone,
            ip_address=ip_address,
            payload_after={"status": "SUCCESS", "channel": "SMS"}
        ))
        db.commit()

        expires_in = settings.OTP_EXPIRY_MINUTES * 60
        sandbox_otp = otp_code if settings.DEV_OTP_SANDBOX_MODE else None

        return True, "OTP sent successfully to registered patient mobile.", sandbox_otp, expires_in

    @staticmethod
    def verify_otp(db: Session, phone_number: str, otp_code: str, receipt_number: Optional[str] = None, ip_address: Optional[str] = None) -> Tuple[bool, str, Optional[str]]:
        """
        Verify submitted OTP against salt-hashed record in healthslip_prod.auth_otps.
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
                action="OTP_VERIFY",
                resource_type="auth_otps",
                resource_id=clean_phone,
                ip_address=ip_address,
                payload_after={"status": "FAILED", "reason": "Expired or not found"}
            ))
            db.commit()
            return False, "OTP has expired or does not exist. Please request a new one.", None

        if record.attempt_count >= settings.OTP_MAX_ATTEMPTS:
            db.add(AuditEvent(
                action="OTP_VERIFY",
                resource_type="auth_otps",
                resource_id=clean_phone,
                ip_address=ip_address,
                payload_after={"status": "BLOCKED", "reason": "Max attempts exceeded"}
            ))
            db.commit()
            return False, "Maximum verification attempts exceeded. Please request a new OTP.", None

        record.attempt_count += 1
        stored_salt, stored_hash = record.otp_hash.split("$", 1)
        computed_hash = OtpService._hash_otp(otp_code.strip(), stored_salt)

        if not hmac.compare_digest(computed_hash, stored_hash):
            db.commit()
            remaining = settings.OTP_MAX_ATTEMPTS - record.attempt_count
            return False, f"Invalid OTP code. {remaining} attempt(s) remaining.", None

        # Verification successful: generate cryptographic session token
        access_token = secrets.token_urlsafe(32)
        record.is_consumed = True
        record.otp_hash = f"VERIFIED:{access_token}"

        db.add(AuditEvent(
            action="OTP_VERIFY",
            resource_type="auth_otps",
            resource_id=clean_phone,
            ip_address=ip_address,
            payload_after={"status": "SUCCESS"}
        ))
        db.commit()

        return True, "Patient identity verified successfully.", access_token

    @staticmethod
    def validate_access_token(db: Session, token: str) -> Optional[AuthOtp]:
        """Validate if patient session token is active in auth_otps (valid for 24 hours)"""
        now = datetime.datetime.utcnow()
        prefix = f"VERIFIED:{token}"
        record = db.query(AuthOtp).filter(
            AuthOtp.otp_hash == prefix,
            AuthOtp.is_consumed == True
        ).first()

        if record:
            if (now - record.created_at).total_seconds() < 86400: # 24 hrs
                return record
        return None
