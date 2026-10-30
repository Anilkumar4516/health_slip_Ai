import os
import json
import logging
import urllib.request
import urllib.parse
import urllib.error
from abc import ABC, abstractmethod
from typing import Tuple, Optional
from app.config import settings

logger = logging.getLogger("healthslip.sms")

class BaseSMSProvider(ABC):
    """Abstract SMS gateway interface for Indian DLT telecommunication compliance"""
    @abstractmethod
    def send_otp(self, phone: str, otp_code: str) -> Tuple[bool, str]:
        pass

class ConsoleMockSMSProvider(BaseSMSProvider):
    """Mock SMS provider for local development, testing, and air-gapped simulation"""
    def send_otp(self, phone: str, otp_code: str) -> Tuple[bool, str]:
        logger.info(f"[SMS Console Mock] 📲 Sent OTP '{otp_code}' to destination '{phone}'")
        print(f"\n[DEV-SMS] >>> Destination: {phone} | OTP: {otp_code} | Expires: {settings.OTP_EXPIRY_MINUTES} mins <<<\n")
        return True, "SMS delivered via Console Mock provider."

class Fast2SMSProvider(BaseSMSProvider):
    """
    Fast2SMS Provider (Indian DLT-compliant SMS Route).
    Sends transaction OTP using Quick Transactional Route or DLT Template.
    """
    def __init__(self, api_key: str, sender_id: Optional[str] = None, template_id: Optional[str] = None):
        self.api_key = api_key
        self.sender_id = sender_id or ""
        self.template_id = template_id or ""
        self.endpoint = "https://www.fast2sms.com/dev/bulkV2"

    def send_otp(self, phone: str, otp_code: str) -> Tuple[bool, str]:
        if not self.api_key:
            logger.error("[Fast2SMS] API key is missing. Cannot send real SMS.")
            return False, "Fast2SMS API key not configured."

        # Clean recipient phone to 10-digit Indian standard
        clean_num = phone.strip().replace(" ", "").replace("-", "")
        if clean_num.startswith("+91"):
            clean_num = clean_num[3:]
        elif clean_num.startswith("91") and len(clean_num) == 12:
            clean_num = clean_num[2:]

        # Payload: DLT route if template_id configured, else quick transactional OTP route
        if self.template_id and self.sender_id:
            payload = {
                "route": "dlt",
                "sender_id": self.sender_id,
                "message": self.template_id,
                "variables_values": otp_code,
                "flash": 0,
                "numbers": clean_num
            }
        else:
            payload = {
                "route": "otp",
                "variables_values": otp_code,
                "flash": 0,
                "numbers": clean_num
            }

        headers = {
            "authorization": self.api_key,
            "Content-Type": "application/json"
        }

        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(self.endpoint, data=req_data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10) as response:
                res_body = response.read().decode("utf-8")
                res_json = json.loads(res_body)
                if res_json.get("return") is True:
                    logger.info(f"[Fast2SMS] OTP sent successfully to {clean_num}")
                    return True, "SMS sent successfully via Fast2SMS."
                else:
                    msg = res_json.get("message", ["Unknown Fast2SMS failure"])[0] if isinstance(res_json.get("message"), list) else str(res_json.get("message"))
                    logger.warning(f"[Fast2SMS] Gateway rejected SMS: {msg}")
                    return False, f"Fast2SMS error: {msg}"
        except Exception as e:
            logger.error(f"[Fast2SMS] Network exception sending SMS to {clean_num}: {e}")
            return False, f"Failed to deliver SMS: {e}"

class MSG91Provider(BaseSMSProvider):
    """
    MSG91 Provider (Enterprise Indian DLT Certified OTP Route).
    API Reference: https://docs.msg91.com/p/tf9GText/send-otp
    """
    def __init__(self, auth_key: str, sender_id: Optional[str] = "HLTSLP", template_id: Optional[str] = None):
        self.auth_key = auth_key
        self.sender_id = sender_id or "HLTSLP"
        self.template_id = template_id or ""
        self.endpoint = "https://control.msg91.com/api/v5/otp"

    def send_otp(self, phone: str, otp_code: str) -> Tuple[bool, str]:
        if not self.auth_key:
            logger.error("[MSG91] Auth Key is missing. Cannot send real SMS.")
            return False, "MSG91 Auth Key not configured."

        clean_num = phone.strip().replace(" ", "").replace("-", "")
        if not clean_num.startswith("+") and not clean_num.startswith("91") and len(clean_num) == 10:
            clean_num = "91" + clean_num
        elif clean_num.startswith("+"):
            clean_num = clean_num[1:]

        params = {
            "template_id": self.template_id,
            "mobile": clean_num,
            "authkey": self.auth_key,
            "otp": otp_code
        }
        query_string = urllib.parse.urlencode({k: v for k, v in params.items() if v})
        full_url = f"{self.endpoint}?{query_string}"

        try:
            req = urllib.request.Request(full_url, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=10) as response:
                res_body = response.read().decode("utf-8")
                res_json = json.loads(res_body)
                if res_json.get("type") == "success":
                    logger.info(f"[MSG91] OTP sent successfully to {clean_num}")
                    return True, "SMS sent successfully via MSG91."
                else:
                    msg = res_json.get("message", "MSG91 failure")
                    logger.warning(f"[MSG91] Rejection: {msg}")
                    return False, f"MSG91 error: {msg}"
        except Exception as e:
            logger.error(f"[MSG91] Network exception sending SMS to {clean_num}: {e}")
            return False, f"Failed to deliver SMS: {e}"

def get_sms_provider() -> BaseSMSProvider:
    """Factory to retrieve active configured SMS provider"""
    provider_name = (settings.SMS_PROVIDER or "console").strip().lower()
    if provider_name == "fast2sms":
        return Fast2SMSProvider(
            api_key=settings.FAST2SMS_API_KEY,
            sender_id=settings.FAST2SMS_SENDER_ID,
            template_id=settings.FAST2SMS_DLT_TE_ID
        )
    elif provider_name == "msg91":
        return MSG91Provider(
            auth_key=settings.MSG91_AUTH_KEY,
            sender_id=settings.MSG91_SENDER_ID,
            template_id=settings.MSG91_DLT_TE_ID
        )
    else:
        return ConsoleMockSMSProvider()
