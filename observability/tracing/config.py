


"""Centralized configuration for tracing."""

import os

from dataclasses import dataclass

def _get_bool(
    name: str,
    default: bool,
) -> bool:
    """Read and validate a boolean environment variable."""

    value = os.getenv(name)

    if value is None:
        return default

    normalized = value.strip().lower()

    if normalized in {"1", "true", "yes", "on"}:
        return True

    if normalized in {"0", "false", "no", "off"}:
        return False

    raise ValueError(
        f"Invalid boolean value for {name}: {value}"
    )

def _get_int(
    name: str,
    default: int,
    minimum: int = 0,
) -> int:
    """Read and validate an integer environment variable."""

    value = os.getenv(name)

    try:
        result = default if value is None else int(value)
    except ValueError as exc:
        raise ValueError(
            f"{name} must be an integer."
        ) from exc

    if result < minimum:
        raise ValueError(
            f"{name} must be greater than or equal to {minimum}."
        )

    return result

@dataclass(frozen=True, slots=True)
class TracingConfig:
    """Tracing runtime configuration."""

    enabled: bool
    content_enabled: bool
    content_preview_chars: int
    max_traced_chunks: int

TRACING_CONFIG = TracingConfig(
    enabled=_get_bool(
        "TRACING_ENABLED",
        True,
    ),
    content_enabled=_get_bool(
        "TRACE_CONTENT_ENABLED",
        True,
    ),
    content_preview_chars=_get_int(
        "TRACE_CONTENT_PREVIEW_CHARS",
        500,
    ),
    max_traced_chunks=_get_int(
        "TRACE_MAX_CHUNKS",
        20,
    ),
)