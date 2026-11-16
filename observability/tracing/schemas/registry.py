



"""Central registry for operation-specific trace schemas."""

from observability.tracing.schemas.ingestion import (
    prepare_chunk_embeddings_inputs,
    prepare_chunk_embeddings_outputs,
    store_chunks_inputs,
    store_chunks_outputs,
)

TRACE_SCHEMAS = {
    "prepare_chunk_embeddings": {
        "process_inputs": prepare_chunk_embeddings_inputs,
        "process_outputs": prepare_chunk_embeddings_outputs,
    },
    "store_chunks": {
        "process_inputs": store_chunks_inputs,
        "process_outputs": store_chunks_outputs,
    },
}