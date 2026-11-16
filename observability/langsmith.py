


"""LangSmith client initialization with centralized privacy protection."""

from functools import lru_cache

from langsmith import Client
from langsmith.run_trees import configure

from observability.privacy.sanitizer import sanitize_langsmith_payload

@lru_cache(maxsize=1)
def get_langsmith_client() -> Client:
    """Create and configure a shared LangSmith client."""

    client = Client(
        anonymizer=sanitize_langsmith_payload,
    )

    configure(client=client)

    return client