




"""Reusable tracing profiles."""

TRACE_PROFILES = {
    "pipeline": {
        "run_type": "chain",
        "tags": ["pipeline"],
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