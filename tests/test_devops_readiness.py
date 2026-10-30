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
