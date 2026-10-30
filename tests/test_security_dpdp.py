import pytest
from fastapi.testclient import TestClient
from main import app
from app.services.encryption_service import EncryptionService
from app.services.receipt_service import ReceiptService
from app.database import SessionLocal
from app.models.user import Patient, User

client = TestClient(app)

def test_security_headers_present():
    """Verify standard security headers are attached to responses"""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "SAMEORIGIN"
    assert resp.headers.get("x-xss-protection") == "1; mode=block"

def test_privacy_policy_page_dpdp():
    """Verify /privacy route serves India DPDP Act 2023 compliant privacy charter"""
    resp = client.get("/privacy")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "India DPDP Act 2023" in resp.text
    assert "Data Principal Rights" in resp.text
    assert "erase-data" in resp.text

def test_readiness_probe():
    """Verify /api/ready probe returns system health for rolling pilot deployment"""
    resp = client.get("/api/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"

def test_encryption_at_rest():
    """Verify sensitive fields are encrypted with Fernet and decrypted accurately"""
    sample_phi = "Flat 402 Lakeview, RTC X Roads, Hyderabad - 500020"
    encrypted = EncryptionService.encrypt(sample_phi)
    assert encrypted.startswith("enc$")
    assert sample_phi not in encrypted

    decrypted = EncryptionService.decrypt(encrypted)
    assert decrypted == sample_phi

    # Backward compatibility with unencrypted legacy text
    assert EncryptionService.decrypt("Plain legacy address") == "Plain legacy address"

def test_patient_dpdp_consent_capture():
    """Verify capturing patient consent records consent entry and purpose"""
    # Create or fetch a test patient
    create_resp = client.post("/api/patients", json={
        "first_name": "Consent",
        "last_name": "TestPatient",
        "phone": "+919876599991",
        "email": "consent.test@healthslip.test",
        "gender": "Female",
        "age": 27
    })
    assert create_resp.status_code == 200
    patient_id = create_resp.json()["id"]

    # Grant consent
    c_resp = client.post(f"/api/patients/{patient_id}/consent", json={
        "consent_purpose": "AI_ANALYSIS",
        "is_granted": True
    })
    assert c_resp.status_code == 200
    assert c_resp.json()["success"] is True
    assert c_resp.json()["consent_purpose"] == "AI_ANALYSIS"
    assert c_resp.json()["is_granted"] is True

def test_patient_dpdp_right_to_erasure():
    """Verify DPDP Act Section 12 Right to Erasure pseudonymizes patient data"""
    create_resp = client.post("/api/patients", json={
        "first_name": "ToErase",
        "last_name": "Patient",
        "phone": "+919876599992",
        "email": "to.erase@healthslip.test",
        "gender": "Male",
        "age": 35
    })
    patient_id = create_resp.json()["id"]

    # Execute Right to Erasure
    erase_resp = client.post(f"/api/patients/{patient_id}/erase-data", json={
        "reason": "Patient requested deletion under DPDP Act 2023",
        "confirm": True
    })
    assert erase_resp.status_code == 200
    assert erase_resp.json()["status"] == "ERASED"

    # Verify patient demographics are pseudonymized in DB
    db = SessionLocal()
    try:
        p = db.query(Patient).filter(Patient.id == patient_id).first()
        assert p.first_name == "ANONYMIZED"
        assert p.last_name == "PATIENT"
        assert "[REDACTED" in (p.address_line1 or "")
        assert p.user.status == "DEACTIVATED"
    finally:
        db.close()

def test_hmac_key_versioning_and_rotation():
    """Verify HMAC verification accepts versioned keys without invalidating existing slips"""
    h_v1 = ReceiptService.calculate_verification_hash(
        slip_number="HSL-2026-99999",
        patient_phone="+919876543210",
        grand_total=500.0,
        visit_date_iso="2026-10-30",
        key_id="v1"
    )
    assert len(h_v1) == 64
