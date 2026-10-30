import pytest
from fastapi.testclient import TestClient
from main import app
from app.config import settings
from app.services.ai_service import AIService
from app.schemas.ai import AIExtractRequest

client = TestClient(app)

def test_ai_draft_status_and_doctor_approval_enforcement():
    """Verify AI parser strictly outputs DRAFT slips requiring doctor approval (never auto-issues)"""
    payload = {
        "clinical_notes": "Patient complains of severe migraine and nausea. Prescribed Ibuprofen 400mg 1 tab BID and Pan-D 1 cap OD."
    }
    resp = client.post("/api/receipts/ai-parse", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "DRAFT"
    assert data["is_draft"] is True
    assert data["requires_doctor_approval"] is True
    assert "mandatory clinical review" in data["clinical_safety_notice"].lower()

def test_de_identification_scrubber():
    """Verify patient identifiers (phone, email, name, address) are stripped before external transit"""
    raw_notes = (
        "Patient: Rajesh Kumar, Phone: +91 98765 43210, Email: rajesh@example.com. "
        "Address: Flat 402 Lakeview Apts, Pincode: 500020. "
        "Complaining of productive cough. Prescribe Augmentin 625mg."
    )
    scrubbed = AIService.scrub_patient_identifiers(raw_notes)
    assert "+91 98765 43210" not in scrubbed
    assert "9876543210" not in scrubbed
    assert "rajesh@example.com" not in scrubbed
    assert "500020" not in scrubbed
    assert "[PHONE_REDACTED]" in scrubbed
    assert "[EMAIL_REDACTED]" in scrubbed
    assert "[PINCODE_REDACTED]" in scrubbed
    assert "[PATIENT_REDACTED]" in scrubbed
    assert "Augmentin 625mg" in scrubbed # Clinical instruction preserved

def test_dosage_and_frequency_edge_cases():
    """Test unit fractions, drops, volume, and frequency abbreviations"""
    # 1. Fraction: 1/2 tablet BID
    p1 = AIService.parse_dosage_and_frequency("take 1/2 tab BID after meals for 5 days")
    assert p1["dosage"] == "1/2 tab"
    assert p1["frequency"] == "BID"
    assert len(p1["slots"]) == 2
    assert p1["duration_days"] == 5

    # 2. Decimal: 0.5 tablet OD
    p2 = AIService.parse_dosage_and_frequency("0.5 tab OD before breakfast for 10 days")
    assert p2["dosage"] == "0.5 tab"
    assert p2["frequency"] == "OD"
    assert p2["meal_relation"] == "BEFORE_MEAL"
    assert p2["duration_days"] == 10

    # 3. Liquid volume: 5 ml TID
    p3 = AIService.parse_dosage_and_frequency("5 ml TID for 3 days")
    assert p3["dosage"] == "5 ml"
    assert p3["frequency"] == "TID"
    assert len(p3["slots"]) == 3
    assert p3["duration_days"] == 3

    # 4. Pediatric Drops: 10 drops SOS
    p4 = AIService.parse_dosage_and_frequency("10 drops SOS when fever")
    assert p4["dosage"] == "10 drops"
    assert p4["frequency"] == "SOS"

    # 5. Night Bedtime: 1 cap HS
    p5 = AIService.parse_dosage_and_frequency("1 cap HS at bedtime")
    assert p5["frequency"] == "HS"
    assert p5["slots"] == ["NIGHT"]

def test_external_ai_optional_flag_fallback():
    """Verify heuristic engine runs safely when ENABLE_EXTERNAL_AI is False"""
    assert settings.ENABLE_EXTERNAL_AI is False
    req = AIExtractRequest(clinical_notes="Patient presents with acute fever and headache. Prescribe Paracetamol 650mg TDS.")
    res = AIService.parse_clinical_notes(req)
    assert res.is_draft is True
    assert len(res.items) >= 2
    assert any("Paracetamol" in it.item_name for it in res.items)
