



"""Guardrails error definitions and classification."""

from typing import Any


class GuardrailError(Exception):
    """Expected error raised during guardrail processing."""

    def __init__(
        self,
        category: str,
        code: str,
        stage: str,
        message: str,
        details: list[dict[str, Any]] | None = None,
    ):
        super().__init__(message)

        self.category = category
        self.code = code
        self.stage = stage
        self.message = message
        self.details = details or []

    def to_dict(self) -> dict[str, Any]:
        """Convert the error into a serializable dictionary."""

        return {
            "category": self.category,
            "code": self.code,
            "stage": self.stage,
            "message": self.message,
            "details": self.details,
        }


def classify_exception(
    exc: Exception,
    stage: str,
) -> dict[str, Any]:
    """Classify expected and unexpected exceptions."""

    if isinstance(exc, GuardrailError):
        return exc.to_dict()

    return {
        "category": "system_error",
        "code": "INTERNAL_GUARDRAIL_ERROR",
        "stage": stage,
        "message": (
            "An internal error occurred while processing guardrails."
        ),
        "details": [],
    }