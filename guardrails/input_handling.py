



"""Input normalization and model response extraction."""

import json
from typing import Any

from .error_classification import GuardrailError


SUPPORTED_MESSAGE_TYPES = {
    "user",
    "model",
}


def _extract_model_text(
    content: Any,
) -> str:
    """Extract text from a model response."""

    if isinstance(content, str):
        return content

    if isinstance(content, dict):

        try:
            return json.dumps(
                content,
                ensure_ascii=False,
            )

        except (TypeError, ValueError) as exc:

            raise GuardrailError(
                category="extraction_error",
                code="MODEL_RESPONSE_EXTRACTION_FAILED",
                stage="response_extraction",
                message="Unable to serialize the model response.",
            ) from exc

    try:
        response_text = content.text

    except Exception as exc:

        raise GuardrailError(
            category="extraction_error",
            code="MODEL_RESPONSE_TEXT_UNAVAILABLE",
            stage="response_extraction",
            message="Unable to extract text from the model response.",
        ) from exc

    if isinstance(response_text, str):
        return response_text

    raise GuardrailError(
        category="extraction_error",
        code="INVALID_MODEL_RESPONSE_TYPE",
        stage="response_extraction",
        message="The model response does not contain valid text.",
    )


def normalize_input(
    content: Any,
    message_type: str,
    max_chars: int = 200_000,
) -> str:
    """Validate and normalize incoming content."""

    if message_type not in SUPPORTED_MESSAGE_TYPES:

        raise GuardrailError(
            category="content_error",
            code="INVALID_MESSAGE_TYPE",
            stage="input_normalization",
            message="Unsupported message type.",
        )

    if message_type == "user":

        if not isinstance(content, str):

            raise GuardrailError(
                category="content_error",
                code="INVALID_USER_INPUT_TYPE",
                stage="input_normalization",
                message="User input must be a string.",
            )

        text = content.strip()

    else:
        text = _extract_model_text(content)

    if not text.strip():

        raise GuardrailError(
            category="content_error",
            code="EMPTY_INPUT",
            stage="input_normalization",
            message="The supplied content is empty.",
        )

    if len(text) > max_chars:

        raise GuardrailError(
            category="content_error",
            code="INPUT_TOO_LARGE",
            stage="input_normalization",
            message="The supplied content exceeds the maximum size.",
        )

    return text