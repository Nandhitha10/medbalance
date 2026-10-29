"""Structured JSON logging for MedBalance services."""

from datetime import datetime, timezone
import json
import logging
import sys
from typing import Any

from medbal_common.settings import get_settings


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def __init__(self, service_name: str = "medbal-service"):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": self.service_name,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        # Include custom extra fields if provided
        standard_attrs = {
            "name", "msg", "args", "levelname", "levelno", "pathname",
            "filename", "module", "exc_info", "exc_text", "stack_info",
            "lineno", "funcName", "created", "msecs", "relativeCreated",
            "thread", "threadName", "processName", "process", "message",
        }
        extras = {k: v for k, v in record.__dict__.items() if k not in standard_attrs}
        if extras:
            log_obj["extra"] = extras

        return json.dumps(log_obj, ensure_ascii=False)


def setup_logging(service_name: str | None = None, level: str | None = None) -> None:
    """Configure root logger with structured JSON formatting."""
    settings = get_settings()
    svc_name = service_name or settings.SERVICE_NAME
    log_level = (level or settings.LOG_LEVEL).upper()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter(service_name=svc_name))

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
