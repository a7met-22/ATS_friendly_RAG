"""Enterprise-grade content policy validation (OWASP LLM Top 10 aligned)."""

import re
import unicodedata
from typing import Any
from observability.tracing import trace_operation


MAX_USER_QUESTION_LENGTH = 1000
_INVISIBLE_CHARS_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\ufeff]")

# كشف السلاسل المشفرة الطويلة (Base64 / Hex) المستخدمة لتهريب الأوامر
_OBFUSCATION_PATTERNS = [
    re.compile(r"\b(?:base64|atob|btoa|fromhex|decode)\b", re.IGNORECASE),
    re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{64,}={0,2}(?![A-Za-z0-9+/=])"),
]


# --------------------------------------------------
# Prompt Injection Patterns
# --------------------------------------------------

PROMPT_INJECTION_PATTERNS = [
    re.compile(
        r"\b(?:ignore|disregard|forget|bypass|override|drop|cancel)\s+"
        r"(?:all\s+|any\s+|every\s+)?"
        r"(?:previous|prior|above|system|safety|initial|original)\s+"
        r"(?:instructions|rules|prompts|restrictions|directives|guidelines)\b",
        re.IGNORECASE,
    ),

    re.compile(
        r"\b(?:act\s+as|pretend\s+to\s+be|roleplay\s+as|you\s+are\s+now|"
        r"switch\s+to|enter\s+developer\s+mode|jailbreak|dan\s+mode)\b",
        re.IGNORECASE,
    ),

    re.compile(
        r"\b(?:reveal|show|print|display|repeat|dump|output|leak|expose)"
        r".{0,50}"
        r"\b(?:system\s+prompt|hidden\s+prompt|developer\s+instructions|"
        r"internal\s+rules|security\s+policy)\b",
        re.IGNORECASE | re.DOTALL,
    ),

    re.compile(
        r"\b(?:api[_ -]?key|secret\s+key|environment\s+variables|"
        r"credentials|passwords|authorized_users_json|\.env)\b",
        re.IGNORECASE,
    ),

    # تغطية الهمزات وصيغ التجاهل والتمثيل في اللغة العربية
    re.compile(
        r"(?:تجاهل|تجاوز|[أإآا]نس[ىي]|خالف|[أإآا]لغ[ِ]?)"
        r".{0,50}"
        r"(?:التعليمات|القواعد|التوجيهات|القيود|الضوابط)",
        re.IGNORECASE | re.DOTALL,
    ),

    re.compile(
        r"(?:تصرف\s+ك[أإآا]نك|تخيل\s+[أإآا]نك|تقمص\s+دور|وضع\s+المطور)",
        re.IGNORECASE,
    ),

    re.compile(
        r"(?:[أإآا]كشف|[أإآا]عرض|[أإآا]طبع|[أإآا]ظهر|سرب)"
        r".{0,50}"
        r"(?:تعليمات\s+النظام|البرومبت|المفاتيح\s+السرية|كلمة\s+المرور|الإعدادات)",
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
        r"(?:poem|story|recipe|essay|article)|"
        r"solve (?:this|the) (?:equation|math problem)|"
        r"translate\s+(?:this|the\s+following)\s+to)\b",
        re.IGNORECASE,
    ),

    re.compile(
        r"(?:ما\s+حالة\s+الطقس|[أإآا]خبار\s+اليوم|[أإآا]خر\s+ال[أإآا]خبار|"
        r"[أإآا]حكيلي\s+نكتة|[أإآا]كتب\s+لي\s+(?:قصيدة|قصة|مقال)|"
        r"[أإآا]عطني\s+وصفة|حل\s+المعادلة|كم\s+الساعة)",
        re.IGNORECASE,
    ),
]


def _normalize_security_text(text: str) -> str:
    """Normalize Unicode homoglyphs and strip invisible control characters."""
    cleaned = _INVISIBLE_CHARS_RE.sub("", text)
    return unicodedata.normalize("NFKC", cleaned)


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

@trace_operation(name="validate_content", profile="pipeline")
def validate_content(
    message_type: str,
    payload: dict[str, Any],
    code_scan: dict[str, Any],
) -> dict[str, Any]:
    """Validate content against application restrictions."""

    raw_text = (
        payload["question"]
        if message_type == "user"
        else payload["answer"]
    )

    # 1. تطبيع النص ضد هجمات التمويه والترميز
    text = _normalize_security_text(raw_text)

    # 2. تقييد طول سؤال المستخدم لمنع استنزاف التوكنز (Denial of Wallet)
    if message_type == "user" and len(text) > MAX_USER_QUESTION_LENGTH:
        return {
            "ok": False,
            "code": "INPUT_LENGTH_EXCEEDED",
            "message": f"Question exceeds maximum allowed length of {MAX_USER_QUESTION_LENGTH} characters.",
            "details": [],
        }

    # 3. كشف التشفير ومحاولات تهريب الأوامر
    if message_type == "user" and _find_matching_pattern(text, _OBFUSCATION_PATTERNS):
        return {
            "ok": False,
            "code": "OBFUSCATED_INPUT_DETECTED",
            "message": "Encoded or obfuscated payloads are not permitted.",
            "details": [],
        }

    # 4. رفض أي أكواد برمجية مكتشفة
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

    # 5. فحص محاولات اختراق الأوامر والأسئلة خارج النطاق
    if message_type == "user":
        if _find_matching_pattern(text, PROMPT_INJECTION_PATTERNS):
            return {
                "ok": False,
                "code": "PROMPT_INJECTION_ATTEMPT",
                "message": "The request contains prohibited instructions.",
                "details": [],
            }

        if _find_matching_pattern(text, OUT_OF_SCOPE_PATTERNS):
            return {
                "ok": False,
                "code": "OUT_OF_SCOPE_REQUEST",
                "message": "Only questions related to uploaded CV documents are permitted.",
                "details": [],
            }

    return {
        "ok": True,
        "code": None,
        "message": None,
        "details": [],
    }
