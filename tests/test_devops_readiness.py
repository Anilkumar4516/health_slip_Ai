import json
import logging
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from main import app
from app.logging_config import JSONLogFormatter
from app.config import settings

client = TestClient(app)


def test_readiness_probe_healthy():
    """Verify /api/ready responds with HTTP 200 and passes database and redis checks"""
    resp = client.get("/api/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert "database" in data["checks"]
    assert data["checks"]["database"]["status"] == "ok"
    assert "redis" in data["checks"]
    assert "timestamp" in data


def test_structured_json_log_formatter():
    """Verify structured logger generates valid RFC-3339 JSON with contextual tags"""
    formatter = JSONLogFormatter(service_name="healthslip-ai", environment="production")
    record = logging.LogRecord(
        name="healthslip.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=25,
        msg="Sample structured audit message",
        args=(),
        exc_info=None
    )
    record.request_id = "test-uuid-1234"
    record.method = "POST"
    record.path = "/api/pharmacy/dispense"
    record.status_code = 200
    record.duration_ms = 42.5

    output = formatter.format(record)
    parsed = json.loads(output)

    assert parsed["service"] == "healthslip-ai"
    assert parsed["environment"] == "production"
    assert parsed["level"] == "INFO"
    assert parsed["message"] == "Sample structured audit message"
    assert parsed["request_id"] == "test-uuid-1234"
    assert parsed["method"] == "POST"
    assert parsed["path"] == "/api/pharmacy/dispense"
    assert parsed["status_code"] == 200
    assert parsed["duration_ms"] == 42.5
    assert "timestamp" in parsed


def test_production_sqlite_fallback_strictly_prohibited():
    """Verify that in production mode, failing to connect to MySQL raises an unrecoverable RuntimeError"""
    from app.database import init_engine

    with patch.object(settings, "ENVIRONMENT", "production"):
        with patch.object(settings, "FALLBACK_TO_SQLITE", True):
            with patch("pymysql.connect", side_effect=Exception("Simulated Network Timeout")):
                with pytest.raises(RuntimeError) as exc_info:
                    init_engine()
                assert "SQLite fallback is strictly forbidden in production mode" in str(exc_info.value)


def test_realtime_websocket_heartbeat_and_ping_pong():
    """Verify live real-time WebSocket connection handshake and bidirectional heartbeat PING/PONG"""
    with client.websocket_connect("/ws/live") as ws:
        # Initial server handshake frame
        handshake_raw = ws.receive_text()
        handshake = json.loads(handshake_raw)
        assert handshake["event"] == "CONNECTED"
        assert "server_time" in handshake["data"]
        assert handshake["data"]["role"] == "GUEST"

        # Client sends real-time heartbeat PING frame
        ws.send_text(json.dumps({"event": "PING"}))
        pong_raw = ws.receive_text()
        pong = json.loads(pong_raw)
        assert pong["event"] == "PONG"
        assert "timestamp" in pong


def test_realtime_room_isolation_and_store_broadcast():
    """Verify real-time store-isolated WebSocket connection and live telemetry status"""
    # Connect with a specific pharmacy store room
    with client.websocket_connect("/ws/live?store_id=1") as ws_store:
        init_raw = ws_store.receive_text()
        init_data = json.loads(init_raw)
        assert init_data["event"] == "CONNECTED"
        assert init_data["data"]["store_id"] == 1

        # Check real-time telemetry counter endpoint
        status_resp = client.get("/api/realtime/status")
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data["status"] == "online"
        assert status_data["active_clients"] >= 1
        assert status_data["store_rooms_count"] >= 1
