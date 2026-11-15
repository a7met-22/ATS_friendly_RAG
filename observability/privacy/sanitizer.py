


"""Centralized data sanitization for observability."""

import json
from collections.abc import Mapping
from typing import Any

from .patterns import redact_secrets
from .presidio_engine import (
    SUPPORTED_ENTITIES,
    get_presidio_engines,
)


REDACTED = "[REDACTED]"

# These fields must never be exposed in observability traces.
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

# Binary content and numerical vectors should not be traced.
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

# Normalize Arabic and Persian digits without changing string length.
DIGIT_TRANSLATION = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹",
    "01234567890123456789",
)


def anonymize_text(value: str) -> str:
    """Detect and anonymize supported PII entities."""

    try:
        analyzer, anonymizer = get_presidio_engines()

        # Normalize digits only for analysis.
        # Each character is replaced with one character, preserving offsets.
        normalized_text = value.translate(DIGIT_TRANSLATION)

        findings = analyzer.analyze(
            text=normalized_text,
            language="en",
            entities=SUPPORTED_ENTITIES,
        )

        # Filter low-confidence phone detections to avoid false positives.
        findings = [
            result
            for result in findings
            if (
                result.entity_type != "PHONE_NUMBER"
                or result.score >= 0.6
            )
        ]

        if findings:
            value = anonymizer.anonymize(
                text=value,
                analyzer_results=findings,
            ).text

        return redact_secrets(value)

    except Exception:
        # Fail closed: never expose unprocessed text.
        return REDACTED

    

def _normalize_key(key: Any) -> str:
    """Normalize dictionary keys before matching."""

    return str(key).strip().lower().replace("-", "_")


def sanitize_value(
    value: Any,
    key: str | None = None,
) -> Any:
    """Recursively sanitize values before observability tracing."""

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

    if not isinstance(inputs, Mapping):
        return {"value": sanitize_value(inputs)}

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

    if not isinstance(outputs, Mapping):
        return {"value": sanitize_value(outputs)}

    return sanitize_value(outputs)


def sanitize_langsmith_payload(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Sanitize the complete LangSmith payload before transmission."""

    try:
        sanitized = sanitize_value(payload)

        if isinstance(sanitized, dict):
            return sanitized

        return {"payload": REDACTED}

    except Exception:
        # Fail closed: do not send any payload if sanitization fails.
        return {
            str(key): REDACTED
            for key in payload
        }