


"""Centralized structured JSON logging with automatic Request-ID correlation and secret redaction."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

# متغير سياقي يحفظ معرف الطلب الحالي تلقائياً عبر جميع الدوال غير المتزامنة (Async Tasks)
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

# أنماط لإخفاء أي توكنات أو مفاتيح سرية قد تظهر بالخطأ في السجلات
_REDACT_PATTERNS = [
    (re.compile(r"(Bearer\s+)[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(api[_-]?key|password|secret|token)([\"':=\s]+)[^\s,\"'}]+", re.IGNORECASE), r"\1\2[REDACTED]"),
]


def _redact_sensitive_text(text: str) -> str:
    cleaned = text
    for pattern, replacement in _REDACT_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)
    return cleaned


class StructuredJsonFormatter(logging.Formatter):
    """Formats every log record as a single-line JSON object for production log aggregators."""

    def format(self, record: logging.LogRecord) -> str:
        message = _redact_sensitive_text(record.getMessage())

        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": request_id_ctx.get(),
            "message": message,
        }

        if record.exc_info:
            exc_text = self.formatException(record.exc_info)
            log_entry["exception"] = _redact_sensitive_text(exc_text)

        return json.dumps(log_entry, ensure_ascii=False)


def configure_logging() -> None:
    """Initialize root and Uvicorn loggers once at application startup."""
    log_level_name = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredJsonFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # توحيد مخرجات خادم Uvicorn لتخرج بنفس تنسيق JSON المنظم
    for uvicorn_logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(uvicorn_logger_name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True
