"""Session-scoped PDF ingestion using the existing RAG pipeline modules."""

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


def _content_hash(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes).hexdigest()


def _get_or_create_session_document(
    *,
    filename: str,
    content_hash: str,
    upload_session_id: str,
) -> tuple[int, str, bool]:
    """Return (document_id, canonical_filename, already_processed).

    A transaction-scoped advisory lock serializes duplicate content checks for
    the same session/hash. The unique content identity is independent of filename.
    """
    metadata = {
        "source_type": "streamlit_upload",
        "upload_session_id": upload_session_id,
        "original_filename": filename,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }

    with get_connection() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s), hashtext(%s))",
                    (upload_session_id, content_hash),
                )
                cur.execute(
                    """
                    SELECT id, filename, status, updated_at
                    FROM public.documents
                    WHERE drive_file_id IS NULL
                      AND content_hash = %s
                      AND metadata->>'source_type' = 'streamlit_upload'
                      AND metadata->>'upload_session_id' = %s
                    ORDER BY id DESC
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (content_hash, upload_session_id),
                )
                existing = cur.fetchone()

                if existing:
                    document_id, canonical_filename, status, updated_at = existing
                    complete = (
                        status == "processed"
                        and document_has_complete_embeddings(conn, document_id)
                    )
                    if complete:
                        return document_id, canonical_filename, True
                    if status == "processing":
                        cur.execute(
                            "SELECT %s::timestamptz < NOW() - INTERVAL '30 minutes'",
                            (updated_at,),
                        )
                        is_stale = cur.fetchone()[0]
                        if not is_stale:
                            raise RuntimeError(
                                f"An identical PDF is already being processed: {canonical_filename}"
                            )
                    set_document_status(conn, document_id, "processing")
                    return document_id, canonical_filename, False

                cur.execute(
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
                document_id = cur.fetchone()[0]
                cur.execute(
                    """
                    INSERT INTO public.document_versions (
                        document_id, version, filename, content_hash, metadata
                    )
                    VALUES (%s, 1, %s, %s, %s)
                    """,
                    (document_id, filename, content_hash, Jsonb(metadata)),
                )
                return document_id, filename, False


def process_uploaded_pdf(
    *,
    pdf_bytes: bytes,
    filename: str,
    upload_session_id: str,
    parser: Callable[[bytes, str], dict[str, Any]],
) -> dict[str, Any]:
    """Process one PDF and persist it in public tables as a session upload."""
    if not pdf_bytes:
        raise ValueError("The uploaded PDF is empty.")
    if b"%PDF-" not in pdf_bytes[:1024]:
        raise ValueError("The uploaded file does not have a valid PDF signature.")
    safe_filename = Path(filename).name
    if not safe_filename.lower().endswith(".pdf"):
        raise ValueError("Only PDF files are supported.")
    if not upload_session_id:
        raise ValueError("Upload session ID is required.")

    digest = _content_hash(pdf_bytes)
    document_id, canonical_filename, reused = _get_or_create_session_document(
        filename=safe_filename,
        content_hash=digest,
        upload_session_id=upload_session_id,
    )
    if reused:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM public.document_chunks WHERE document_id = %s",
                    (document_id,),
                )
                chunk_count = cur.fetchone()[0]
        return {
            "document_id": document_id,
            "filename": canonical_filename,
            "content_hash": digest,
            "chunk_count": chunk_count,
            "reused": True,
        }

    try:
        processed = process_pdf_bytes(
            pdf_bytes=pdf_bytes,
            filename=safe_filename,
            parser=parser,
            specialization=None,
        )
        chunks = processed.get("chunks") if isinstance(processed, dict) else None
        if not isinstance(chunks, list) or not chunks:
            raise ValueError(f"No text chunks were generated for {safe_filename}.")

        vectors = prepare_chunk_embeddings(
            document_name=safe_filename,
            chunks=chunks,
            specialization=None,
        )
        if len(vectors) != len(chunks):
            raise ValueError("Embedding count does not match chunk count.")

        with get_connection() as conn:
            with conn.transaction():
                store_chunks(
                    conn=conn,
                    document_id=document_id,
                    chunks=chunks,
                    embeddings=vectors,
                    specialization=None,
                    replace_existing=True,
                )
                set_document_status(conn, document_id, "processed")

        return {
            "document_id": document_id,
            "filename": safe_filename,
            "content_hash": digest,
            "chunk_count": len(chunks),
            "reused": False,
        }

    except Exception:
        try:
            with get_connection() as conn:
                with conn.transaction():
                    set_document_status(conn, document_id, "failed")
        except Exception:
            pass
        raise
