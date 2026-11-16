"""Centralized data sanitization for observability."""

from collections.abc import Mapping
from typing import Any

from observability.privacy.patterns import redact_secrets
from observability.privacy.presidio_engine import (
    SUPPORTED_ENTITIES,
    get_presidio_engines,
)

REDACTED = "[REDACTED]"

SENSITIVE_KEYS = {
    "password",
    "secret",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "authorization",
    "email",
    "email_address",
    "phone",
    "phone_number",
    "national_id",
    "national_id_number",
    "passport",
    "passport_number",
    "card_number",
    "credit_card_number",
    "bank_account_number",
    "iban",
    "iban_code",
    "ssn",
    "social_security_number",
    "cvv",
}

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

DIGIT_TRANSLATION = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹",
    "01234567890123456789",
)

PHONE_CONFIDENCE_THRESHOLD = 0.6

def anonymize_text(value: str) -> str:
    """Detect and anonymize sensitive entities in text."""

    if not isinstance(value, str):
        return REDACTED

    try:
        analyzer, anonymizer = get_presidio_engines()

        normalized_text = value.translate(DIGIT_TRANSLATION)

        findings = analyzer.analyze(
            text=normalized_text,
            language="en",
            entities=SUPPORTED_ENTITIES,
        )

        findings = [
            result
            for result in findings
            if (
                result.entity_type != "PHONE_NUMBER"
                or result.score >= PHONE_CONFIDENCE_THRESHOLD
            )
        ]

        if findings:
            value = anonymizer.anonymize(
                text=value,
                analyzer_results=findings,
            ).text

        return redact_secrets(value)

    except Exception:
        return REDACTED

def _normalize_key(key: Any) -> str:
    """Normalize dictionary keys for sensitive-field matching."""

    return (
        str(key)
        .strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )

def sanitize_value(
    value: Any,
    key: str | None = None,
) -> Any:
    """Recursively sanitize values before sending them to LangSmith."""

    normalized_key = _normalize_key(key) if key is not None else ""

    if normalized_key in SENSITIVE_KEYS:
        return REDACTED

    if normalized_key in NON_TEXT_KEYS:
        return REDACTED

    if isinstance(value, str):
        return anonymize_text(value)

    if isinstance(value, (bytes, bytearray, memoryview)):
        return REDACTED

    if isinstance(value, Mapping):
        sanitized = {}

        for item_key, item_value in value.items():
            sanitized[str(item_key)] = sanitize_value(
                item_value,
                str(item_key),
            )

        return sanitized

    if isinstance(value, (list, tuple)):
        return [
            sanitize_value(item)
            for item in value
        ]

    if isinstance(value, set):
        return [
            sanitize_value(item)
            for item in sorted(value, key=str)
        ]

    if value is None or isinstance(value, (bool, int, float)):
        return value

    return f"[UNSUPPORTED_TYPE: {type(value).__name__}]"

def sanitize_langsmith_payload(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Sanitize the complete payload before LangSmith receives it."""

    try:
        sanitized = sanitize_value(payload)

        if isinstance(sanitized, dict):
            return sanitized

        return {"payload": REDACTED}

    except Exception:
        return {
            str(key): REDACTED
            for key in payload
        }