



"""Content policy validation."""

import re

from typing import Any


# --------------------------------------------------
# Prompt Injection Patterns
# --------------------------------------------------

PROMPT_INJECTION_PATTERNS = [

    re.compile(
        r"\bignore\s+(?:all\s+)?"
        r"(?:previous|prior|above)\s+instructions\b",
        re.IGNORECASE,
    ),

    re.compile(
        r"\bdisregard\s+(?:all\s+)?"
        r"(?:previous|prior|above)\s+instructions\b",
        re.IGNORECASE,
    ),

    re.compile(
        r"\b(?:reveal|show|print|display|repeat)"
        r".{0,50}"
        r"\b(?:system prompt|hidden prompt|developer instructions)\b",
        re.IGNORECASE | re.DOTALL,
    ),

    re.compile(
        r"\b(?:api[_ -]?key|secret key|environment variables|"
        r"credentials|passwords)\b",
        re.IGNORECASE,
    ),

    re.compile(
        r"(?:تجاهل|تجاوز)"
        r".{0,50}"
        r"(?:التعليمات|القواعد|التوجيهات)",
        re.IGNORECASE | re.DOTALL,
    ),

    re.compile(
        r"(?:اكشف|اعرض|اطبع)"
        r".{0,50}"
        r"(?:تعليمات النظام|البرومبت|المفاتيح السرية|كلمة المرور)",
        re.IGNORECASE | re.DOTALL,
    ),

]


# --------------------------------------------------
# Clearly Unrelated Request Patterns
# --------------------------------------------------

OUT_OF_SCOPE_PATTERNS = [

    re.compile(
        r"\b(?:what(?:'s| is) the weather|weather forecast|"
        r"latest news|stock price|exchange rate|"
        r"tell me a joke|write (?:me )?(?:a )?"
        r"(?:poem|story|recipe)|"
        r"solve (?:this|the) (?:equation|math problem))\b",
        re.IGNORECASE,
    ),

    re.compile(
        r"(?:ما حالة الطقس|اخبار اليوم|آخر الأخبار|"
        r"احكيلي نكتة|اكتب لي قصيدة|"
        r"اعطني وصفة|حل المعادلة|كم الساعة)",
        re.IGNORECASE,
    ),

]


def _find_matching_pattern(
    text: str,
    patterns: list[re.Pattern],
) -> bool:
    """Check whether any policy pattern matches."""

    return any(
        pattern.search(text)
        for pattern in patterns
    )


# --------------------------------------------------
# Content Validation
# --------------------------------------------------

def validate_content(
    message_type: str,
    payload: dict[str, Any],
    code_scan: dict[str, Any],
) -> dict[str, Any]:
    """Validate content against application restrictions."""

    text = (
        payload["question"]
        if message_type == "user"
        else payload["answer"]
    )

    # Reject detected code or execution patterns.
    if code_scan["detected"]:

        findings = code_scan["findings"]

        is_code_request = any(
            finding["category"] == "code_request"
            for finding in findings
        )

        if message_type == "user" and is_code_request:

            return {
                "ok": False,
                "code": "PROHIBITED_CODE_REQUEST",
                "message": "Programming requests are not permitted.",
                "details": findings,
            }

        return {
            "ok": False,
            "code": "PROHIBITED_CODE_CONTENT",
            "message": "Programming code or execution patterns are not permitted.",
            "details": findings,
        }

    # Check prompt injection and restricted information requests.
    if message_type == "user":

        if _find_matching_pattern(
            text,
            PROMPT_INJECTION_PATTERNS,
        ):

            return {
                "ok": False,
                "code": "PROMPT_INJECTION_ATTEMPT",
                "message": "The request contains prohibited instructions.",
                "details": [],
            }

        # Reject clearly unrelated requests.
        if _find_matching_pattern(
            text,
            OUT_OF_SCOPE_PATTERNS,
        ):

            return {
                "ok": False,
                "code": "OUT_OF_SCOPE_REQUEST",
                "message": (
                    "Only questions related to uploaded CV documents are permitted."
                ),
                "details": [],
            }

    return {
        "ok": True,
        "code": None,
        "message": None,
        "details": [],
    }