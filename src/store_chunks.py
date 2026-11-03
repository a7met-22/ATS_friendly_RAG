


"""Prepare chunk embeddings and persist chunks in PostgreSQL."""

import json
import math
from typing import Any


from src.embeddings import (
    EMBEDDING_DIMENSIONS,
    EMBED_MODEL_NAME,
    generate_embeddings,
)


def build_embedding_text(
    document_name: str,
    chunk: dict[str, Any],
    specialization: str | None = None,
) -> str:
    """Combine document name, section, specialization, and content."""

    metadata = chunk.get("metadata") or {}

    section = metadata.get("section") or ""

    specialization_value = (
        specialization
        or metadata.get("specialization")
        or metadata.get("area_of_expertise")
        or ""
    )

    return "\n".join(
        [
            f"Document: {document_name}",
            f"Section: {section}",
            f"Specialization: {specialization_value}",
            "Chunk content:",
            chunk["content"],
        ]
    ).strip()


def prepare_chunk_embeddings(
    document_name: str,
    chunks: list[dict[str, Any]],
    specialization: str | None = None,
) -> list[list[float]]:
    """Generate one document embedding for each chunk."""

    if not chunks:
        raise ValueError(
            "Cannot generate embeddings for an empty chunk list."
        )

    texts = []

    for index, chunk in enumerate(chunks):

        content = chunk.get("content")

        if (
            not isinstance(content, str)
            or not content.strip()
        ):
            raise ValueError(
                f"Chunk {index} has empty or invalid content."
            )

        metadata = chunk.get("metadata") or {}

        if not isinstance(metadata, dict):
            raise ValueError(
                f"Chunk {index} metadata must be a dictionary."
            )

        texts.append(
            build_embedding_text(
                document_name,
                chunk,
                specialization,
            )
        )


    vectors = generate_embeddings(
        texts,
        task_type="RETRIEVAL_DOCUMENT",
    )

    if len(vectors) != len(chunks):
        raise RuntimeError(
            "Embedding count does not match chunk count."
        )

    return vectors


def store_chunks(
    conn,
    document_id: int,
    chunks: list[dict[str, Any]],
    embeddings: list[list[float]],
    specialization: str | None = None,
    replace_existing: bool = True,
) -> int:
    """Store chunks and embeddings using the caller's connection.

    The caller is responsible for opening and committing the transaction.
    """

    if not chunks:
        raise ValueError(
            "Cannot store an empty chunk list."
        )

    if len(chunks) != len(embeddings):
        raise ValueError(
            "Chunk and embedding counts do not match."
        )

    normalized_rows = []

    seen_indexes = set()

    for position, (chunk, vector) in enumerate(
        zip(chunks, embeddings, strict=True)
    ):

        content = chunk.get("content")

        if (
            not isinstance(content, str)
            or not content.strip()
        ):
            raise ValueError(
                f"Chunk {position} has empty or invalid content."
            )

        chunk_index = chunk.get(
            "chunk_index",
            position,
        )

        if (
            isinstance(chunk_index, bool)
            or not isinstance(chunk_index, int)
            or chunk_index < 0
        ):
            raise ValueError(
                f"Invalid chunk index: {chunk_index}"
            )

        if chunk_index in seen_indexes:
            raise ValueError(
                f"Duplicate chunk index: {chunk_index}"
            )

        seen_indexes.add(chunk_index)

        if len(vector) != EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"Expected {EMBEDDING_DIMENSIONS} embedding values; "
                f"got {len(vector)}."
            )

        vector_values = [
            float(value)
            for value in vector
        ]

        if not all(
            math.isfinite(value)
            for value in vector_values
        ):
            raise ValueError(
                f"Chunk {position} embedding contains invalid values."
            )

        metadata = dict(
            chunk.get("metadata") or {}
        )

        if specialization and not metadata.get("specialization"):
            metadata["specialization"] = specialization

        metadata["_embedding"] = {
            "model": EMBED_MODEL_NAME,
            "dimensions": EMBEDDING_DIMENSIONS,
            "normalized": True,
        }

        vector_literal = (
            "["
            + ",".join(
                format(value, ".10g")
                for value in vector_values
            )
            + "]"
        )

        normalized_rows.append(
            (
                document_id,
                chunk_index,
                content,
                json.dumps(
                    metadata,
                    ensure_ascii=False,
                ),
                vector_literal,
            )
        )

    with conn.cursor() as cur:

        # Verify document existence.
        cur.execute(
            """
            SELECT id
            FROM public.documents
            WHERE id = %s
            """,
            (document_id,),
        )

        if cur.fetchone() is None:
            raise ValueError(
                f"Document {document_id} does not exist."
            )

        # Replace old chunks when processing a new document version.
        if replace_existing:

            cur.execute(
                """
                DELETE FROM public.document_chunks
                WHERE document_id = %s
                """,
                (document_id,),
            )

        cur.executemany(
            """
            INSERT INTO public.document_chunks (
                document_id,
                chunk_index,
                content,
                metadata,
                embedding
            )
            VALUES (
                %s, %s, %s, %s::jsonb, %s::vector
            )
            """,
            normalized_rows,
        )

    return len(normalized_rows)
