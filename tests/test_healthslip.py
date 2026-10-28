import pytest
from fastapi.testclient import TestClient
from main import app
from app.database import Base, engine, SessionLocal
from app.services.receipt_service import ReceiptService
from app.services.otp_service import OtpService
from app.services.ai_service import AIService
from app.schemas.ai import AIExtractRequest

client = TestClient(app)

def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "database" in data

def test_ai_clinical_parsing():
    req = AIExtractRequest(
        clinical_notes="Patient Minh Nguyen, 28/M, presents with acute migraine. Prescribe Ibuprofen 400mg 1 pill after lunch for 5 days. Consultation fee $50.",
        patient_name="Minh",
        patient_age=28,
        patient_gender="Male",
        patient_phone="+1 555-019-2834"
    )
    result = AIService.parse_clinical_notes(req)
    assert "Minh" in result.patient_name
    assert any("Ibuprofen" in item.item_name for item in result.items)
    assert any("CONSULTATION" == item.item_type for item in result.items)
    assert len(result.reminders) > 0
    assert len(result.safety_warnings) > 0

def test_receipt_creation_and_tamper_proofing():
    # 1. Create a receipt via API
    payload = {
        "patient": {
            "full_name": "Minh",
            "age": 28,
            "gender": "Male",
            "phone": "+15550192834"
        },
        "doctor_name": "Dr. Minh Nguyen, M.D.",
        "doctor_license": "MED-2024-8841",
        "clinic_name": "HealthSlip AI Medical Center",
        "diagnosis": "Acute Tension Migraine",
        "symptoms": "Headache, fatigue",
        "items": [
            {
                "item_type": "CONSULTATION",
                "item_name": "Physician Consultation",
                "unit_price": 50.0,
                "quantity": 1
            },
            {
                "item_type": "MEDICATION",
                "item_name": "Ibuprofen 400mg",
                "unit_price": 12.0,
                "quantity": 2
            }
        ],
        "reminders": [
            {
                "medicine_name": "Ibuprofen",
                "dosage": "1 pill",
                "timing_slot": "MORNING",
                "schedule_time": "12:00 am",
                "duration_days": 5
            }
        ],
        "tax_percent": 5.0,
        "discount_amount": 0.0,
        "payment_status": "PAID"
    }

    response = client.post("/api/receipts", json=payload)
    assert response.status_code == 200
    data = response.json()
    slip_number = data["slip_number"]
    assert slip_number.startswith("HSL-")
    assert data["subtotal"] == 74.0 # 50 + 24
    assert data["tax_amount"] == 3.70 # 5% of 74
    assert data["grand_total"] == 77.70
    assert len(data["verification_hash"]) == 64 # SHA-256 hex length

    # 2. Public Verification check
    v_resp = client.get(f"/api/verify/{slip_number}")
    assert v_resp.status_code == 200
    v_data = v_resp.json()
    assert v_data["is_valid"] is True
    assert v_data["tamper_proof_status"] == "AUTHENTIC & VERIFIED"
    assert "M***" in v_data["patient_masked_name"]

    # 3. PDF Generation check
    pdf_resp = client.get(f"/api/receipts/{data['id']}/pdf")
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert len(pdf_resp.content) > 1000

def test_otp_flow_and_patient_slip_access():
    import random
    phone = f"+1999{random.randint(1000000, 9999999)}"
    # 1. Request OTP
    req_resp = client.post("/api/otp/request", json={"phone_number": phone})
    assert req_resp.status_code == 200
    req_data = req_resp.json()
    assert req_data["success"] is True
    sandbox_otp = req_data["sandbox_otp"]
    assert sandbox_otp is not None
    assert len(sandbox_otp) == 6

    # 2. Rate limit test: requesting immediately within 60s cooldown should be rejected
    rate_resp = client.post("/api/otp/request", json={"phone_number": phone})
    assert rate_resp.status_code == 429

    # 3. Verify OTP
    verify_resp = client.post("/api/otp/verify", json={
        "phone_number": phone,
        "otp_code": sandbox_otp
    })
    assert verify_resp.status_code == 200
    verify_data = verify_resp.json()
    assert verify_data["success"] is True
    token = verify_data["access_token"]
    assert token is not None

    # 4. Access secured patient slips with token
    slips_resp = client.get("/api/otp/patient-slips", headers={"X-Patient-Token": token})
    assert slips_resp.status_code == 200

def test_reminders_toggle():
    # Fetch reminders
    resp = client.get("/api/reminders")
    assert resp.status_code == 200
    reminders = resp.json()
    assert len(reminders) > 0

    first_rem = reminders[0]
    initial_status = first_rem["is_done"]

    # Toggle
    toggle_resp = client.post(f"/api/reminders/{first_rem['id']}/toggle")
    assert toggle_resp.status_code == 200
    assert toggle_resp.json()["is_done"] != initial_status

def test_auth_doctor_login_and_logout():
    # 1. Login with Doctor credentials
    login_resp = client.post("/api/auth/login", json={
        "email_or_phone": "dr.minh@healthslip.ai",
        "password": "Doctor@2026"
    })
    assert login_resp.status_code == 200
    data = login_resp.json()
    assert data["success"] is True
    token = data["access_token"]
    assert token is not None
    assert data["user"]["primary_role"] == "DOCTOR"
    assert "MED-2024-8841" in (data["user"]["practitioner_license"] or "")

    # 2. Access /api/auth/me with Bearer token
    me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "dr.minh@healthslip.ai"

    # 3. Check active sessions endpoint
    sess_resp = client.get("/api/auth/sessions", headers={"Authorization": f"Bearer {token}"})
    assert sess_resp.status_code == 200
    sessions = sess_resp.json()
    assert len(sessions) > 0
    assert any(s["is_current"] for s in sessions)

    # 4. Perform real-time logout
    logout_resp = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout_resp.status_code == 200
    assert logout_resp.json()["success"] is True

    # 5. Token must now be strictly rejected (401 Unauthorized)
    me_after = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_after.status_code == 401

def test_auth_invalid_credentials():
    # Attempt login with wrong password
    bad_resp = client.post("/api/auth/login", json={
        "email_or_phone": "dr.minh@healthslip.ai",
        "password": "WrongPassword@123"
    })
    assert bad_resp.status_code == 401
    assert "Invalid" in bad_resp.json()["detail"]

def test_auth_register_and_status():
    import random
    unique_suffix = random.randint(100000, 999999)
    email = f"nurse.test_{unique_suffix}@healthslip.ai"
    phone = f"+1888{unique_suffix}"

    # 1. Register new account
    reg_resp = client.post("/api/auth/register", json={
        "full_name": f"Nurse Test {unique_suffix}",
        "email": email,
        "phone_number": phone,
        "password": "SecurePassword@2026",
        "role_code": "PATIENT"
    })
    assert reg_resp.status_code == 200
    reg_data = reg_resp.json()
    assert reg_data["success"] is True
    token = reg_data["access_token"]

    # 2. Check /api/auth/status
    st_resp = client.get("/api/auth/status", headers={"Authorization": f"Bearer {token}"})
    assert st_resp.status_code == 200
    st_data = st_resp.json()
    assert st_data["authenticated"] is True
    assert st_data["user"]["email"] == email

    # 3. Logout
    client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})

