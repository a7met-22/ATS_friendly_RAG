




"""Guardrails debugging and response reporting."""

import json
from typing import Any


def display_model_response(
    raw_response: str | None,
    parsed_data: dict[str, Any] | None = None,
    extracted_text: str | None = None,
    checks: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> None:
    """Display raw and processed model responses."""

    print("\n" + "=" * 70)
    print("RAW MODEL RESPONSE")
    print("=" * 70)

    print(
        raw_response
        if raw_response is not None
        else "Raw response unavailable."
    )

    print("\n" + "=" * 70)
    print("VALIDATED JSON")
    print("=" * 70)

    if parsed_data is not None:

        print(
            json.dumps(
                parsed_data,
                ensure_ascii=False,
                indent=2,
            )
        )

    else:

        print("JSON extraction or validation failed.")

    print("\n" + "=" * 70)
    print("EXTRACTED ANSWER")
    print("=" * 70)

    print(
        extracted_text
        if extracted_text is not None
        else "No extracted answer available."
    )

    print("\n" + "=" * 70)
    print("GUARDRAIL CHECKS")
    print("=" * 70)

    print(
        json.dumps(
            checks or {},
            ensure_ascii=False,
            indent=2,
        )
    )

    if error is not None:

        print("\n" + "=" * 70)
        print("ERROR DETAILS")
        print("=" * 70)

        print(
            json.dumps(
                error,
                ensure_ascii=False,
                indent=2,
            )
        )

    print("\n" + "=" * 70)