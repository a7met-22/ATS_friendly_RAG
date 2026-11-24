"""Idempotent, zero-downtime PostgreSQL & pgvector schema bootstrap and dimension validator."""

from __future__ import annotations

import logging

from config.settings import EMBEDDING_DIMENSION
from database_utilities.database_connection import get_connection

logger = logging.getLogger(__name__)

_SCHEMA_BOOTSTRAP_LOCK_ID = 847291034


def _get_validated_dimension() -> int:
    dim = int(EMBEDDING_DIMENSION)
    if dim <= 0 or dim > 16_000:
        raise ValueError(f"Invalid EMBEDDING_DIMENSION configured: {dim}")
    return dim


def _build_ddl_statements(dim: int) -> tuple[str, ...]:
    return (
        "CREATE EXTENSION IF NOT EXISTS vector",
        """
        CREATE TABLE IF NOT EXISTS public.documents (
            id BIGSERIAL PRIMARY KEY,
            drive_file_id TEXT UNIQUE,
            filename TEXT NOT NULL,
            content_hash TEXT,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "ALTER TABLE public.documents ADD COLUMN IF NOT EXISTS content_hash TEXT",
        "ALTER TABLE public.documents ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
        f"""
        CREATE TABLE IF NOT EXISTS public.document_chunks (
            id BIGSERIAL PRIMARY KEY,
            document_id BIGINT NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            embedding vector({dim}) NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (document_id, chunk_index)
        )
        """,
    )


_CONCURRENT_INDEX_STATEMENTS: tuple[str, ...] = (
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_document_chunks_embedding_hnsw
        ON public.document_chunks
        USING hnsw (embedding vector_cosine_ops)
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_document_chunks_content_fts_gin
        ON public.document_chunks
        USING gin (to_tsvector('simple', coalesce(content, '')))
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_document_chunks_document_id
        ON public.document_chunks (document_id)
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_documents_session_scope
        ON public.documents ((metadata->>'upload_session_id'), created_at)
        WHERE drive_file_id IS NULL
    """,
)


async def _verify_vector_dimension(cur, expected_dim: int) -> None:
    """Fail fast at startup if the existing DB column dimension differs from EMBEDDING_DIMENSION."""
    await cur.execute(
        """
        SELECT format_type(a.atttypid, a.atttypmod)
        FROM pg_attribute a
        JOIN pg_class c ON a.attrelid = c.oid
        JOIN pg_namespace n ON c.relnamespace = n.oid
        WHERE n.nspname = 'public'
          AND c.relname = 'document_chunks'
          AND a.attname = 'embedding'
          AND a.attnum > 0
          AND NOT a.attisdropped
        """
    )
    row = await cur.fetchone()
    if row and row[0]:
        expected_type = f"vector({expected_dim})"
        if row[0] != expected_type:
            raise RuntimeError(
                f"FATAL: Database embedding column is '{row[0]}', "
                f"but EMBEDDING_DIMENSION is configured as '{expected_type}'."
            )


async def ensure_database_schema() -> None:
    """Verify schema, validate vector dimensions, and create concurrent indexes safely across workers."""
    dim = _get_validated_dimension()
    ddl_statements = _build_ddl_statements(dim)

    # 1. إنشاء الجداول والتحقق من الأبعاد داخل معاملة محمية بقفل المعاملة
    async with await get_connection() as conn:
        async with conn.transaction():
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT pg_advisory_xact_lock(%s)",
                    (_SCHEMA_BOOTSTRAP_LOCK_ID,),
                )
                for stmt in ddl_statements:
                    await cur.execute(stmt)
                await _verify_vector_dimension(cur, dim)

    # 2. بناء الفهارس بـ CONCURRENTLY خارج المعاملة مع قفل جلسة لمنع تصادم الـ Workers
    async with await get_connection() as conn:
        await conn.set_autocommit(True)
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT pg_advisory_lock(%s)",
                    (_SCHEMA_BOOTSTRAP_LOCK_ID + 1,),
                )
                try:
                    for idx_stmt in _CONCURRENT_INDEX_STATEMENTS:
                        await cur.execute(idx_stmt)
                finally:
                    await cur.execute(
                        "SELECT pg_advisory_unlock(%s)",
                        (_SCHEMA_BOOTSTRAP_LOCK_ID + 1,),
                    )
        finally:
            await conn.set_autocommit(False)

    logger.info("Database schema, vector dimension (%d), and indexes verified successfully.", dim)
