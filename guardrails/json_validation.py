



"""Strict JSON extraction and schema validation."""

import json
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    ValidationError,
)

from .error_classification import GuardrailError


# --------------------------------------------------
# JSON Schemas
# --------------------------------------------------

class UserPayload(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    question: str = Field(min_length=1)


class Citation(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    document_title: str = Field(min_length=1)
    chunk_id: StrictStr | StrictInt


class ModelPayload(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    answer: str = Field(min_length=1)
    citations: list[Citation]


# --------------------------------------------------
# Strict JSON Parser
# --------------------------------------------------

class DuplicateJSONKeyError(ValueError):
    """Raised when a JSON object contains duplicate keys."""


def _reject_duplicate_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    """Reject duplicate JSON keys."""

    result = {}

    for key, value in pairs:

        if key in result:
            raise DuplicateJSONKeyError(key)

        result[key] = value

    return result


def _reject_nonstandard_constants(value: str):
    """Reject NaN and Infinity JSON values."""

    raise ValueError(
        f"Invalid JSON constant: {value}"
    )


def parse_json_strict(
    raw_text: str,
) -> dict[str, Any]:
    """Parse a complete JSON object without prefixes or suffixes."""

    try:

        parsed = json.loads(
            raw_text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonstandard_constants,
        )

    except DuplicateJSONKeyError as exc:

        raise GuardrailError(
            category="extraction_error",
            code="DUPLICATE_JSON_KEY",
            stage="json_extraction",
            message="JSON contains duplicate object keys.",
        ) from exc

    except (json.JSONDecodeError, ValueError, TypeError) as exc:

        raise GuardrailError(
            category="extraction_error",
            code="INVALID_JSON_FORMAT",
            stage="json_extraction",
            message=(
                "The content is not a valid standalone JSON object."
            ),
        ) from exc

    if not isinstance(parsed, dict):

        raise GuardrailError(
            category="extraction_error",
            code="INVALID_JSON_ROOT",
            stage="json_extraction",
            message="The JSON root must be an object.",
        )

    return parsed


# --------------------------------------------------
# Schema Validation
# --------------------------------------------------

def _validate_schema(
    payload: dict[str, Any],
    schema: type[BaseModel],
    schema_name: str,
) -> dict[str, Any]:
    """Validate a dictionary against a Pydantic schema."""

    try:

        validated = schema.model_validate(payload)

    except ValidationError as exc:

        validation_details = []

        for error in exc.errors(
            include_context=False,
            include_url=False,
        ):

            validation_details.append({
                "field": ".".join(
                    str(item)
                    for item in error["loc"]
                ),
                "issue": error["msg"],
            })

        raise GuardrailError(
            category="extraction_error",
            code="SCHEMA_VALIDATION_FAILED",
            stage="schema_validation",
            message=f"Invalid {schema_name} JSON structure.",
            details=validation_details,
        ) from exc

    return validated.model_dump(
        mode="json",
    )


# --------------------------------------------------
# Main JSON Extraction Function
# --------------------------------------------------

def extract_and_validate(
    text: str,
    message_type: str,
) -> dict[str, Any]:
    """Extract, validate, and normalize the message JSON."""

    if message_type == "user":

        # Convert the original question into JSON.
        serialized = json.dumps(
            {
                "question": text,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

        # Verify that the generated JSON is valid.
        parsed = parse_json_strict(serialized)

        data = _validate_schema(
            payload=parsed,
            schema=UserPayload,
            schema_name="user",
        )

        extracted_text = data["question"]

    elif message_type == "model":

        # Parse the complete raw model response.
        parsed = parse_json_strict(text)

        data = _validate_schema(
            payload=parsed,
            schema=ModelPayload,
            schema_name="model",
        )

        extracted_text = data["answer"]

    else:

        raise GuardrailError(
            category="content_error",
            code="INVALID_MESSAGE_TYPE",
            stage="json_extraction",
            message="Unsupported message type.",
        )

    # Generate one canonical JSON representation.
    json_text = json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    return {
        "data": data,
        "json_text": json_text,
        "extracted_text": extracted_text,
    }