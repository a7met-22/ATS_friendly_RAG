


"""Additional patterns for detecting technical secrets."""

import re


SECRET_PATTERNS = [


    (
        re.compile(
            r"""(?i)\b(?:password|passwd|secret|api[_-]?key|"""
            r"""access[_-]?token|refresh[_-]?token|client[_-]?secret)"""
            r"""\s*[:=]\s*["']?[^\s,;"']+"""
        ),
        "[REDACTED_SECRET]",
    ),
    (
        re.compile(
            r"""(?i)\bhttps?://[^/\s:@]+:[^@\s/]+@"""
        ),
        "https://[REDACTED]@",
    ),
    (
        re.compile(
            r"\beyJ[A-Za-z0-9_-]{10,}\."
            r"[A-Za-z0-9_-]{10,}\."
            r"[A-Za-z0-9_-]{10,}\b"
        ),
        "[REDACTED_JWT]",
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
    (
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "[REDACTED_AWS_KEY]",
    ),
    (
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]+\b"),
        "[REDACTED_SLACK_TOKEN]",
    ),
    (
        re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{10,}\b"),
        "[REDACTED_PAYMENT_KEY]",
    ),
]


def redact_secrets(value: str) -> str:
    """Redact recognizable technical secrets."""

    for pattern, replacement in SECRET_PATTERNS:
        value = pattern.sub(replacement, value)

    return value