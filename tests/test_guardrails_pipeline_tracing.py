


"""Test hierarchical LangSmith tracing for Guardrails."""

from guardrails.pipeline import inspect_message

import pytest

from guardrails.pipeline import inspect_message


"""Test JSON extraction and validation through the Guardrails pipeline."""


@pytest.mark.parametrize(
    ("content", "expected_status", "expected_ok"),
    [
        # Valid JSON with a question.
        (
            '{"question": "Explain RAG"}',
            "accepted",
            True,
        ),

        # Duplicate JSON keys.
        (
            '{"question": "First question", "question": "Second question"}',
            "rejected",
            False,
        ),

        # Malformed JSON.
        (
            '{"question": "Explain RAG"',
            "rejected",
            False,
        ),

        # Valid JSON, but missing the required question field.
        (
            '{"name": "Ahmed"}',
            "rejected",
            False,
        ),
    ],
)
def test_json_extraction_and_validation(
    content,
    expected_status,
    expected_ok,
):
    """Validate JSON extraction and schema validation."""

    result = inspect_message(
        content=content,
        message_type="user",
        debug=True,
    )

    print("\nInput:", content)
    print("Extracted text:", result.get("extracted_text"))
    print("JSON text:", result.get("json_text"))
    print("Checks:", result.get("checks"))
    print("Error:", result.get("error"))

    assert result["status"] == expected_status
    assert result["ok"] is expected_ok
