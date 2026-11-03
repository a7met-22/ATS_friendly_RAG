


"""Semantic vector retrieval using PostgreSQL and pgvector."""

from database_utilities.database_connection import get_connection

from src.embeddings import generate_embeddings


def _validate_document_ids(
    document_ids: list[int] | None,
) -> list[int]:
    """Validate and deduplicate selected document IDs."""

    if not document_ids:
        return []

    if any(
        isinstance(document_id, bool)
        or not isinstance(document_id, int)
        or document_id <= 0
        for document_id in document_ids
    ):
        raise ValueError(
            "All document IDs must be positive integers."
        )

    return list(
        dict.fromkeys(document_ids)
    )


def _vector_literal(
    vector: list[float],
) -> str:
    """Convert an embedding to pgvector literal format."""

    return (
        "["
        + ",".join(
            format(float(value), ".10g")
            for value in vector
        )
        + "]"
    )


def semantic_search(
    query: str,
    top_k: int = 5,
    document_ids: list[int] | None = None,
) -> list[dict]:
    """Retrieve semantically similar chunks from selected documents."""

    if (
        not isinstance(query, str)
        or not query.strip()
    ):
        raise ValueError(
            "Query cannot be empty."
        )

    if (
        isinstance(top_k, bool)
        or not isinstance(top_k, int)
        or top_k < 1
    ):
        raise ValueError(
            "top_k must be a positive integer."
        )

    selected_ids = _validate_document_ids(
        document_ids
    )

    if not selected_ids:
        return []

    # Generate query embedding.
    query_embedding = generate_embeddings(
        [query.strip()],
        task_type="RETRIEVAL_QUERY",
    )[0]

    embedding_literal = _vector_literal(
        query_embedding
    )

    with get_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    d.id AS document_id,
                    d.filename AS document_title,
                    c.id AS chunk_id,
                    c.content,
                    c.chunk_index,
                    c.metadata,
                    c.embedding <=> %s::vector AS distance

                FROM public.document_chunks AS c

                JOIN public.documents AS d
                    ON d.id = c.document_id

                WHERE d.status = 'processed'
                  AND c.embedding IS NOT NULL
                  AND d.id = ANY(%s::bigint[])

                ORDER BY c.embedding <=> %s::vector

                LIMIT %s
                """,
                (
                    embedding_literal,
                    selected_ids,
                    embedding_literal,
                    top_k,
                ),
            )

            rows = cur.fetchall()

    return [
        {
            "document_id": row[0],
            "document_title": row[1],
            "chunk_id": row[2],
            "content": row[3],
            "chunk_index": row[4],
            "metadata": row[5],
            "distance": float(row[6]),
            "retrieval_method": "semantic",
        }
        for row in rows
    ]