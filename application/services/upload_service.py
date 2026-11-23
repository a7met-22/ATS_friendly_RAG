"""Async session-scoped PDF ingestion using the existing RAG pipeline modules."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from psycopg.types.json import Jsonb

from database_utilities.database_connection import get_connection
from database_utilities.document_utilities import (
    document_has_complete_embeddings,
    set_document_status,
)
from src.document_processor import process_pdf_bytes
from src.store_chunks import prepare_chunk_embeddings, store_chunks

MAX_PDF_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB limit per uploaded PDF


def _content_hash(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes).hexdigest()


async def _get_or_create_session_document(
    *,
    filename: str,
    content_hash: str,
    upload_session_id: str,
    source_type: str = "session_upload",
) -> tuple[int, str, bool]:
    """Return (document_id, canonical_filename, already_processed).

    A transaction-scoped advisory lock serializes duplicate content checks for
    the same session/hash. The unique content identity is independent of filename.
    """
    metadata = {
        "source_type": source_type,
        "upload_session_id": upload_session_id,
        "original_filename": filename,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }

    async with await get_connection() as conn:
        async with conn.transaction():
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s), hashtext(%s))",
                    (upload_session_id, content_hash),
                )
                await cur.execute(
                    """
                    SELECT id, filename, status, updated_at
                    FROM public.documents
                    WHERE drive_file_id IS NULL
                      AND content_hash = %s
                      AND metadata->>'source_type' IN ('session_upload', 'streamlit_upload')
                      AND metadata->>'upload_session_id' = %s
                    ORDER BY id DESC
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (content_hash, upload_session_id),
                )
                existing = await cur.fetchone()

                if existing:
                    document_id, canonical_filename, status, updated_at = existing
                    complete = (
                        status == "processed"
                        and await document_has_complete_embeddings(conn, document_id)
                    )
                    if complete:
                        return document_id, canonical_filename, True

                    if status == "processing":
                        await cur.execute(
                            "SELECT %s::timestamptz < NOW() - INTERVAL '30 minutes'",
                            (updated_at,),
                        )
                        row = await cur.fetchone()
                        is_stale = bool(row[0]) if row else False
                        if not is_stale:
                            raise RuntimeError(
                                f"An identical PDF is already being processed: {canonical_filename}"
                            )

                    await set_document_status(conn, document_id, "processing")
                    return document_id, canonical_filename, False

                await cur.execute(
                    """
                    INSERT INTO public.documents (
                        filename, drive_file_id, drive_folder_id, content_hash,
                        version, status, metadata
                    )
                    VALUES (%s, NULL, NULL, %s, 1, 'processing', %s)
                    RETURNING id
                    """,
                    (filename, content_hash, Jsonb(metadata)),
                )
                doc_row = await cur.fetchone()
                if not doc_row:
                    raise RuntimeError("Failed to insert session document record.")
                document_id = doc_row[0]

                await cur.execute(
                    """
                    INSERT INTO public.document_versions (
                        document_id, version, filename, content_hash, metadata
                    )
                    VALUES (%s, 1, %s, %s, %s)
                    """,
                    (document_id, filename, content_hash, Jsonb(metadata)),
                )
                return document_id, filename, False


async def process_uploaded_pdf(
    *,
    pdf_bytes: bytes,
    filename: str,
    upload_session_id: str,
    parser: Callable[[bytes, str], Any],
    source_type: str = "session_upload",
) -> dict[str, Any]:
    """Process one PDF asynchronously and persist it in public tables as a session upload."""
    if not pdf_bytes:
        raise ValueError("The uploaded PDF is empty.")
    if len(pdf_bytes) > MAX_PDF_SIZE_BYTES:
        raise ValueError("The uploaded PDF exceeds the maximum allowed size of 20 MB.")
    if b"%PDF-" not in pdf_bytes[:1024]:
        raise ValueError("The uploaded file does not have a valid PDF signature.")

    safe_filename = Path(filename).name
    if not safe_filename.lower().endswith(".pdf"):
        raise ValueError("Only PDF files are supported.")
    if not upload_session_id or not isinstance(upload_session_id, str):
        raise ValueError("Upload session ID is required.")

    digest = _content_hash(pdf_bytes)
    document_id, canonical_filename, reused = await _get_or_create_session_document(
        filename=safe_filename,
        content_hash=digest,
        upload_session_id=upload_session_id,
        source_type=source_type,
    )

    if reused:
        async with await get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT COUNT(*) FROM public.document_chunks WHERE document_id = %s",
                    (document_id,),
                )
                count_row = await cur.fetchone()
                chunk_count = count_row[0] if count_row else 0

        return {
            "document_id": document_id,
            "filename": canonical_filename,
            "content_hash": digest,
            "chunk_count": chunk_count,
            "reused": True,
        }

    try:
        processed = await process_pdf_bytes(
            pdf_bytes=pdf_bytes,
            filename=safe_filename,
            parser=parser,
            specialization=None,
        )
        chunks = processed.get("chunks") if isinstance(processed, dict) else None
        if not isinstance(chunks, list) or not chunks:
            raise ValueError(f"No text chunks were generated for {safe_filename}.")

        vectors = await prepare_chunk_embeddings(
            document_name=safe_filename,
            chunks=chunks,
            specialization=None,
        )
        if not vectors or len(vectors) != len(chunks):
            raise ValueError("Embedding count does not match chunk count.")

        async with await get_connection() as conn:
            async with conn.transaction():
                await store_chunks(
                    conn=conn,
                    document_id=document_id,
                    chunks=chunks,
                    embeddings=vectors,
                    specialization=None,
                    replace_existing=True,
                )
                await set_document_status(conn, document_id, "processed")

        return {
            "document_id": document_id,
            "filename": safe_filename,
            "content_hash": digest,
            "chunk_count": len(chunks),
            "reused": False,
        }

    except Exception:
        try:
            async with await get_connection() as conn:
                async with conn.transaction():
                    await set_document_status(conn, document_id, "failed")
        except Exception:
            pass
        raise

async def cleanup_expired_session_uploads(max_age_hours: int = 24) -> int:
    """Delete temporary session-uploaded documents older than max_age_hours."""
    async with await get_connection() as conn:
        async with conn.transaction():
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    DELETE FROM public.documents
                    WHERE drive_file_id IS NULL
                      AND metadata->>'source_type' IN ('session_upload', 'streamlit_upload')
                      AND created_at < NOW() - make_interval(hours => %s)
                    """,
                    (max_age_hours,),
                )
                return cur.rowcount or 0

# Clean up expired session uploads in bounded batches to avoid long-running transactions
async def cleanup_expired_session_uploads(max_age_hours: int = 24, batch_size: int = 500) -> int:
    """Delete expired temporary session-uploaded documents in bounded batches."""
    async with await get_connection() as conn:
        async with conn.transaction():
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    WITH expired AS (
                        SELECT id
                        FROM public.documents
                        WHERE drive_file_id IS NULL
                          AND metadata->>'source_type' IN ('session_upload', 'streamlit_upload')
                          AND created_at < NOW() - make_interval(hours => %s)
                        LIMIT %s
                    )
                    DELETE FROM public.documents
                    WHERE id IN (SELECT id FROM expired)
                    """,
                    (max_age_hours, batch_size),
                )
                return cur.rowcount or 0
