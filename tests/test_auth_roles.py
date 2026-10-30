import pytest
from fastapi.testclient import TestClient
from main import app
from app.services.auth_service import AuthService
from app.database import SessionLocal
from app.models.user import User

client = TestClient(app)

def test_pharmacist_jwt_login_and_store_profile():
    """Verify pharmacist logs in with credentials, receives access+refresh JWTs, and store details"""
    response = client.post("/api/auth/login", json={
        "email_or_phone": "pharmacist@healthslip.ai",
        "password": "Pharmacist@2026",
        "remember_me": True
    })
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["success"] is True
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["primary_role"] == "PHARMACIST"
    assert data["user"]["store_id"] is not None
    assert "Central Pharmacy" in (data["user"]["store_name"] or "")
    assert data["user"]["pharmacist_registration"] == "TSPC-2024-48912"

def test_jwt_refresh_token_rotation():
    """Verify refresh token endpoint issues a fresh valid access token"""
    login_resp = client.post("/api/auth/login", json={
        "email_or_phone": "pharmacist@healthslip.ai",
        "password": "Pharmacist@2026"
    })
    assert login_resp.status_code == 200
    refresh_token = login_resp.json()["refresh_token"]

    # Refresh
    refresh_resp = client.post("/api/auth/refresh", json={
        "refresh_token": refresh_token
    })
    assert refresh_resp.status_code == 200, refresh_resp.text
    ref_data = refresh_resp.json()
    assert ref_data["success"] is True
    assert "access_token" in ref_data
    assert ref_data["token_type"] == "bearer"
    assert ref_data["user"]["primary_role"] == "PHARMACIST"

def test_websocket_room_status_and_auth():
    """Verify WebSocket status endpoint shows room metrics"""
    status_resp = client.get("/api/realtime/status")
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["status"] == "online"
    assert "store_rooms_count" in data
    assert "patient_rooms_count" in data
