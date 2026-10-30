import json
import logging
import sys
import uuid
import time
from datetime import datetime, timezone
from typing import Any, Dict


class JSONLogFormatter(logging.Formatter):
    """
    Structured JSON log formatter for cloud-native production environments.
    Outputs machine-readable logs compatible with CloudWatch, Datadog, Loki, and ELK.
    """
    def __init__(self, service_name: str = "healthslip-ai", environment: str = "production"):
        super().__init__()
        self.service_name = service_name
        self.environment = environment

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self.service_name,
            "environment": self.environment,
        }

        # Include contextual fields if present
        for field in ("request_id", "method", "path", "status_code", "duration_ms", "client_ip"):
            if hasattr(record, field):
                log_entry[field] = getattr(record, field)

        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            log_entry.update(record.extra_data)

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(level: str = "INFO", environment: str = "development") -> logging.Logger:
    """Configures structured logging for the application"""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    if environment.lower() == "production":
        handler.setFormatter(JSONLogFormatter(service_name="healthslip-ai", environment=environment))
    else:
        handler.setFormatter(logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))

    root_logger.addHandler(handler)
    return logging.getLogger("healthslip")
