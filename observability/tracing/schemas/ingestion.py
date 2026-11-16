


"""Trace data mapping for document ingestion operations."""

from collections.abc import Mapping
from typing import Any

from observability.tracing.config import TRACING_CONFIG

CHUNK_METADATA_FIELDS = (
    "section",
    "page",
    "specialization",
    "area_of_expertise",
)

def _extract_output(
    outputs: Any,
) -> Any:
    """Extract the actual function output from a trace payload."""

    if isinstance(outputs, Mapping):
        return outputs.get("output")

    return outputs

def _summarize_chunks(
    chunks: Any,
) -> dict[str, Any]:
    """Create a bounded and privacy-controlled chunk summary."""

    if not isinstance(chunks, (list, tuple)):
        chunks = []

    summaries = []

    for index, chunk in enumerate(
        chunks[:TRACING_CONFIG.max_traced_chunks]
    ):
        if not isinstance(chunk, Mapping):
            continue

        content = chunk.get("content", "")
        metadata = chunk.get("metadata") or {}

        if not isinstance(content, str):
            content = ""

        if not isinstance(metadata, Mapping):
            metadata = {}

        summary = {
            "chunk_index": chunk.get("chunk_index", index),
            "content_length": len(content),
            "metadata": {
                key: metadata[key]
                for key in CHUNK_METADATA_FIELDS
                if key in metadata
            },
        }

        if TRACING_CONFIG.content_enabled:
            summary["content_preview"] = content[
                :TRACING_CONFIG.content_preview_chars
            ]

        summaries.append(summary)

    return {
        "chunks_count": len(chunks),
        "traced_chunks_count": len(summaries),
        "chunks_truncated": (
            len(chunks) > TRACING_CONFIG.max_traced_chunks
        ),
        "chunks": summaries,
    }

def prepare_chunk_embeddings_inputs(
    inputs: Any,
) -> dict[str, Any]:
    """Map embedding preparation inputs into a trace-safe structure."""

    try:
        if not isinstance(inputs, Mapping):
            return {"trace_mapping_error": True}

        chunks = inputs.get("chunks") or []

        return {
            "document_name": inputs.get("document_name"),
            "specialization": inputs.get("specialization"),
            **_summarize_chunks(chunks),
        }

    except Exception:
        return {"trace_mapping_error": True}

def prepare_chunk_embeddings_outputs(
    outputs: Any,
) -> dict[str, Any]:
    """Map embedding preparation outputs into trace metadata."""

    try:
        vectors = _extract_output(outputs)

        if not isinstance(vectors, (list, tuple)):
            vectors = []

        first_vector = vectors[0] if vectors else []

        dimensions = (
            len(first_vector)
            if isinstance(first_vector, (list, tuple))
            else 0
        )

        return {
            "embedding_count": len(vectors),
            "embedding_dimensions": dimensions,
        }

    except Exception:
        return {"trace_mapping_error": True}

def store_chunks_inputs(
    inputs: Any,
) -> dict[str, Any]:
    """Map chunk storage inputs without exposing database identifiers."""

    try:
        if not isinstance(inputs, Mapping):
            return {"trace_mapping_error": True}

        chunks = inputs.get("chunks") or []
        embeddings = inputs.get("embeddings") or []

        if not isinstance(embeddings, (list, tuple)):
            embeddings = []

        first_vector = embeddings[0] if embeddings else []

        dimensions = (
            len(first_vector)
            if isinstance(first_vector, (list, tuple))
            else 0
        )

        return {
            **_summarize_chunks(chunks),
            "embedding_count": len(embeddings),
            "embedding_dimensions": dimensions,
            "replace_existing": inputs.get("replace_existing"),
        }

    except Exception:
        return {"trace_mapping_error": True}

def store_chunks_outputs(
    outputs: Any,
) -> dict[str, Any]:
    """Map chunk storage results."""

    try:
        result = _extract_output(outputs)

        return {
            "stored_count": result,
        }

    except Exception:
        return {"trace_mapping_error": True}