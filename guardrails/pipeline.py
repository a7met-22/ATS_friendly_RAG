



"""Main guardrails validation pipeline."""

import logging
from typing import Any

from .input_handling import normalize_input
from .json_validation import extract_and_validate
from .code_detection import scan_code_patterns
from .content_validation import validate_content
from .error_classification import (
    GuardrailError,
    classify_exception,
)
from .reporting import display_model_response


logger = logging.getLogger(__name__)


CHECK_NAMES = (
    "input_validation",
    "json_validation",
    "schema_validation",
    "code_detection",
    "content_validation",
)


def inspect_message(
    content: Any,
    message_type: str,
    *,
    debug: bool = False,
    max_chars: int = 200_000,
) -> dict[str, Any]:
    """
    Validate a user message or model response.

    Supported message types:
        - user
        - model
    """

    checks = {
        name: None
        for name in CHECK_NAMES
    }

    current_stage = "input_normalization"

    normalized_text = None
    data = None
    json_text = None
    extracted_text = None
    error = None

    try:

        # ------------------------------------------
        # 1. Input Handling
        # ------------------------------------------

        normalized_text = normalize_input(
            content=content,
            message_type=message_type,
            max_chars=max_chars,
        )

        checks["input_validation"] = True

        # ------------------------------------------
        # 2. JSON Extraction and Schema Validation
        # ------------------------------------------

        current_stage = "json_extraction"

        extraction = extract_and_validate(
            text=normalized_text,
            message_type=message_type,
        )

        data = extraction["data"]
        json_text = extraction["json_text"]
        extracted_text = extraction["extracted_text"]

        checks["json_validation"] = True
        checks["schema_validation"] = True

        # ------------------------------------------
        # 3. Code Detection
        # ------------------------------------------

        current_stage = "code_detection"

        code_scan = scan_code_patterns(
            text=extracted_text,
            message_type=message_type,
        )

        checks["code_detection"] = not code_scan["detected"]

        # ------------------------------------------
        # 4. Content Validation
        # ------------------------------------------

        current_stage = "content_validation"

        validation = validate_content(
            message_type=message_type,
            payload=data,
            code_scan=code_scan,
        )

        checks["content_validation"] = validation["ok"]

        if not validation["ok"]:

            raise GuardrailError(
                category="content_error",
                code=validation["code"],
                stage="content_validation",
                message=validation["message"],
                details=validation["details"],
            )

        # ------------------------------------------
        # 5. Successful Result
        # ------------------------------------------

        result = {
            "ok": True,
            "status": "accepted",
            "message_type": message_type,
            "data": data,
            "json_text": json_text,
            "extracted_text": extracted_text,
            "checks": checks,
            "error": None,
        }

    except Exception as exc:

        # Keep JSON validation status accurate when
        # JSON parsing succeeds but schema validation fails.
        if (
            isinstance(exc, GuardrailError)
            and exc.stage == "schema_validation"
        ):
            checks["json_validation"] = True

        error = classify_exception(
            exc=exc,
            stage=current_stage,
        )

        if error["category"] == "system_error":

            logger.exception(
                "Unexpected guardrail error at stage: %s",
                current_stage,
            )

        status = (
            "rejected"
            if error["category"] == "content_error"
            else "error"
        )

        result = {
            "ok": False,
            "status": status,
            "message_type": message_type,
            "data": None,
            "json_text": None,
            "extracted_text": None,
            "checks": checks,
            "error": error,
        }

    # ----------------------------------------------
    # 6. Optional Model Response Reporting
    # ----------------------------------------------

    if debug and message_type == "model":

        display_model_response(
            raw_response=normalized_text,
            parsed_data=data,
            extracted_text=extracted_text,
            checks=checks,
            error=error,
        )

    return result