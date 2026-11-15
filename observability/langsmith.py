"""LangSmith tracing integration with centralized privacy protection."""

from functools import lru_cache

from langsmith import Client, traceable
from langsmith.run_trees import configure

from .privacy import sanitize_langsmith_payload


TRACE_PROFILES = {
    "pipeline": {
        "run_type": "chain",
        "tags": ["guardrails", "pipeline"],
    },
    "llm": {
        "run_type": "llm",
        "tags": ["ai", "generation"],
    },
    "embedding": {
        "run_type": "embedding",
        "tags": ["rag", "embeddings"],
    },
    "parser": {
        "run_type": "parser",
        "tags": ["parsing"],
    },
}


@lru_cache(maxsize=1)
def get_langsmith_client() -> Client:
    """Create one LangSmith client with centralized anonymization."""

    return Client(
        anonymizer=sanitize_langsmith_payload,
    )


def trace_operation(
    *,
    name: str,
    profile: str = "pipeline",
    tags: list[str] | None = None,
    metadata: dict | None = None,
    run_type: str | None = None,
):
    """Trace an operation using a predefined profile and privacy policy."""

    if profile not in TRACE_PROFILES:
        raise ValueError(f"Unknown trace profile: {profile}")

    profile_config = TRACE_PROFILES[profile]
    client = get_langsmith_client()

    # Apply the protected client as the default tracing client.
    configure(client=client)

    resolved_tags = [
        *profile_config["tags"],
        *(tags or []),
    ]

    resolved_metadata = {
        "trace_profile": profile,
        **(metadata or {}),
    }

    return traceable(
        name=name,
        run_type=run_type or profile_config["run_type"],
        tags=resolved_tags,
        metadata=resolved_metadata,
        client=client,
    )