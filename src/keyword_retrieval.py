




"""Keyword retrieval using PostgreSQL Full-Text Search."""

from database_utilities.database_connection import get_connection


TEXT_SEARCH_CONFIG = "simple"


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


def keyword_search(
    query: str,
    top_k: int = 5,
    document_ids: list[int] | None = None,
) -> list[dict]:
    """Retrieve chunks using PostgreSQL Full-Text Search.

    The simple configuration avoids English-only stemming.
    It supports token-based matching for English and Arabic,
    but does not provide Arabic morphological stemming.
    """

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

                    ts_rank_cd(
                        c.search_vector,
                        plainto_tsquery(
                            %s::regconfig,
                            %s
                        )
                    ) AS rank

                FROM public.document_chunks AS c

                JOIN public.documents AS d
                    ON d.id = c.document_id

                WHERE d.status = 'processed'

                  AND d.id = ANY(%s::bigint[])

                  AND c.search_vector @@ plainto_tsquery(
                      %s::regconfig,
                      %s
                  )

                ORDER BY rank DESC, c.id

                LIMIT %s
                """,
                (
                    TEXT_SEARCH_CONFIG,
                    query.strip(),
                    selected_ids,
                    TEXT_SEARCH_CONFIG,
                    query.strip(),
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
            "keyword_rank": float(row[6]),
            "retrieval_method": "keyword",
        }
        for row in rows
    ]