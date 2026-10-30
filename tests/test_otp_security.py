import pytest
import secrets
from fastapi.testclient import TestClient
from main import app
from app.config import settings
from app.services.sms_provider import get_sms_provider, ConsoleMockSMSProvider, Fast2SMSProvider, MSG91Provider
from app.services.otp_service import OtpService
from app.database import SessionLocal
from app.models.verification import AuthOtp

client = TestClient(app)

def test_sms_provider_factory_and_mock():
    """Verify default SMS provider is ConsoleMockSMSProvider and dispatches correctly"""
    provider = get_sms_provider()
    assert isinstance(provider, ConsoleMockSMSProvider)
    ok, msg = provider.send_otp("+919876543210", "123456")
    assert ok is True
    assert "Mock" in msg

def test_otp_60s_cooldown_blocking():
    """Verify consecutive OTP requests within 60s cooldown are blocked with 429"""
    phone = f"+9198{secrets.randbelow(89999999)+10000000}"
    # First request succeeds
    r1 = client.post("/api/otp/request", json={"phone_number": phone})
    assert r1.status_code == 200, r1.text

    # Immediate second request should be blocked by cooldown
    r2 = client.post("/api/otp/request", json={"phone_number": phone})
    assert r2.status_code == 429
    assert "Please wait" in r2.json()["detail"]

def test_otp_lockout_after_3_attempts():
    """Verify after 3 incorrect verification attempts, user is locked out"""
    phone = f"+9197{secrets.randbelow(89999999)+10000000}"
    # Request OTP
    r_req = client.post("/api/otp/request", json={"phone_number": phone})
    assert r_req.status_code == 200

    # 3 incorrect attempts
    for attempt in range(1, 4):
        r_fail = client.post("/api/otp/verify", json={"phone_number": phone, "otp_code": "000000"})
        assert r_fail.status_code == 400
        assert "attempt(s) remaining" in r_fail.json()["detail"]

    # 4th attempt should be locked out
    r_locked = client.post("/api/otp/verify", json={"phone_number": phone, "otp_code": "000000"})
    assert r_locked.status_code == 400
    assert "Maximum verification attempts exceeded" in r_locked.json()["detail"]

def test_production_otp_suppression(monkeypatch):
    """Verify sandbox_otp is never returned in API responses when in production"""
    phone = f"+9196{secrets.randbelow(89999999)+10000000}"
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "DEBUG", False)

    r = client.post("/api/otp/request", json={"phone_number": phone})
    assert r.status_code == 200
    data = r.json()
    assert data["sandbox_otp"] is None, "Sandbox OTP must be None in production"
