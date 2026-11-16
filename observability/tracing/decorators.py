



"""Reusable LangSmith tracing decorators."""

from collections.abc import Callable
from functools import wraps
from typing import Any

from langsmith import traceable

from observability.langsmith import get_langsmith_client
from observability.tracing.config import TRACING_CONFIG
from observability.tracing.profiles import TRACE_PROFILES
from observability.tracing.schemas.registry import TRACE_SCHEMAS

def trace_operation(
    *,
    name: str,
    profile: str = "pipeline",
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    run_type: str | None = None,
) -> Callable:
    """Decorate an operation with centralized LangSmith tracing."""

    if not isinstance(name, str) or not name.strip():
        raise ValueError("Trace name must be a non-empty string.")

    if profile not in TRACE_PROFILES:
        raise ValueError(
            f"Unknown tracing profile: {profile}"
        )

    if tags is not None and not isinstance(tags, list):
        raise TypeError("tags must be a list of strings.")

    if metadata is not None and not isinstance(metadata, dict):
        raise TypeError("metadata must be a dictionary.")

    profile_config = TRACE_PROFILES[profile]
    schema = TRACE_SCHEMAS.get(name, {})

    def decorator(func: Callable) -> Callable:
        if not TRACING_CONFIG.enabled:
            return func

        client = get_langsmith_client()

        traced_function = traceable(
            name=name,
            run_type=run_type or profile_config["run_type"],
            tags=[
                *profile_config["tags"],
                *(tags or []),
            ],
            metadata={
                "trace_profile": profile,
                **(metadata or {}),
            },
            client=client,
            process_inputs=schema.get("process_inputs"),
            process_outputs=schema.get("process_outputs"),
        )(func)

        return traced_function

    return decorator