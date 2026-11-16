


"""Secret detection and redaction patterns."""

import re

SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"""(?ix)
        \b(
            api[_-]?key |
            access[_-]?token |
            refresh[_-]?token |
            client[_-]?secret |
            password |
            secret
        )\b
        (\s*[:=]\s*)
        (["']?)
        [^\s,;'"<>]+
        \3
        """
    ),
    re.compile(
        r"\bBearer\s+[A-Za-z0-9._~+/=-]+",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bsk-[A-Za-z0-9_-]{12,}\b",
        re.IGNORECASE,
    ),
)

def redact_secrets(value: str) -> str:
    """Redact recognizable credentials and secret tokens."""

    if not isinstance(value, str):
        return value

    for pattern in SECRET_PATTERNS:
        value = pattern.sub("[REDACTED_SECRET]", value)

    return value