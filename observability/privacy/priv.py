


"""Centralized data protection for observability.

Replaced And depend on LangSmith's Presidio-based anonymization"""

import json
import re
from functools import lru_cache
from typing import Any, Mapping

from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine


REDACTED = "[REDACTED]"

# Values under these keys must never be sent to observability.
SENSITIVE_KEYS = {
    "password",
    "secret",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "authorization",
    "email",
    "phone",
    "address",
    "national_id",
    "passport",
    "card_number",
    "cvv",
}

# Binary data and numerical vectors are excluded from traces.
NON_TEXT_KEYS = {
    "pdf_bytes",
    "file_bytes",
    "raw_file",
    "image_bytes",
    "audio_bytes",
    "embedding",
    "embeddings",
    "vector",
    "vectors",
}

# Additional patterns for common secrets.
PATTERNS = [
    (
        re.compile(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
        ),
        "[REDACTED_EMAIL]",
    ),
    (
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
        "Bearer [REDACTED]",
    ),
    (
        re.compile(
            r"\b(?:sk-[A-Za-z0-9_-]{12,}|"
            r"AIza[A-Za-z0-9_-]{20,}|"
            r"gh[pousr]_[A-Za-z0-9]{20,})\b"
        ),
        "[REDACTED_API_KEY]",
    ),
]


@lru_cache(maxsize=1)
def _get_presidio_engines():
    """Initialize Presidio engines once and reuse them."""

    return AnalyzerEngine(), AnonymizerEngine()


def _redact_patterns(value: str) -> str:
    """Redact common sensitive patterns as an additional safeguard."""

    for pattern, replacement in PATTERNS:
        value = pattern.sub(replacement, value)

    return value


def anonymize_text(value: str) -> str:
    """Detect and anonymize PII in text before tracing."""

    try:
        analyzer, anonymizer = _get_presidio_engines()

        findings = analyzer.analyze(
            text=value,
            language="en",
        )

        if findings:
            value = anonymizer.anonymize(
                text=value,
                analyzer_results=findings,
            ).text

        return _redact_patterns(value)

    except Exception:
        # Fail closed: never send unprocessed text to observability.
        return REDACTED


def _normalize_key(key: Any) -> str:
    """Normalize dictionary keys for consistent matching."""

    return str(key).strip().lower().replace("-", "_")


def sanitize_value(
    value: Any,
    key: str | None = None,
) -> Any:
    """Recursively sanitize values before sending them to observability."""

    normalized_key = _normalize_key(key) if key else ""

    if normalized_key in SENSITIVE_KEYS:
        return REDACTED

    if normalized_key in NON_TEXT_KEYS:
        return REDACTED

    if isinstance(value, str):
        return anonymize_text(value)

    if isinstance(value, (bytes, bytearray, memoryview)):
        return REDACTED

    if isinstance(value, Mapping):
        return {
            str(item_key): sanitize_value(item_value, str(item_key))
            for item_key, item_value in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [
            sanitize_value(item)
            for item in value
        ]

    if value is None or isinstance(value, (bool, int, float)):
        return value

    # Avoid exposing arbitrary object representations.
    return f"[UNSUPPORTED_TYPE: {type(value).__name__}]"


def sanitize_trace_inputs(
    inputs: dict[str, Any],
) -> dict[str, Any]:
    """Sanitize inputs before sending them to LangSmith."""

    sanitized = sanitize_value(inputs)

    content = inputs.get("content")

    if content is not None:
        sanitized["content_type"] = type(content).__name__

        try:
            content_text = (
                content
                if isinstance(content, str)
                else json.dumps(
                    content,
                    ensure_ascii=False,
                    default=str,
                )
            )
            sanitized["content_length"] = len(content_text)

        except (TypeError, ValueError):
            sanitized["content_length"] = None

    return sanitized


def sanitize_trace_outputs(
    outputs: dict[str, Any],
) -> dict[str, Any]:
    """Sanitize outputs before sending them to LangSmith."""

    return sanitize_value(outputs)

