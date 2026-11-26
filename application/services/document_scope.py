"""Resolve and enforce the document scope available to a user (Async)."""

from __future__ import annotations

import asyncio
from database_utilities.database_connection import get_connection
from security.authorization import (
    PERMISSION_SYSTEM_SEARCH,
    Principal,
    require_permission,
)


async def get_session_upload_ids(upload_session_id: str) -> list[int]:
    """Retrieve processed document IDs uploaded during the current session."""
    if not upload_session_id or not isinstance(upload_session_id, str):
        return []

    async with await get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id
                FROM public.documents
                WHERE drive_file_id IS NULL
                  AND status = 'processed'
                  AND metadata->>'source_type' IN ('session_upload', 'streamlit_upload')
                  AND metadata->>'upload_session_id' = %s
                ORDER BY created_at, id
                """,
                (upload_session_id,),
            )
            rows = await cur.fetchall()
            return [row[0] for row in rows]


async def get_system_document_ids(principal: Principal | None) -> list[int]:
    """Retrieve all processed system document IDs for authorized principals."""
    require_permission(principal, PERMISSION_SYSTEM_SEARCH)

    async with await get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id
                FROM public.documents
                WHERE drive_file_id IS NOT NULL
                  AND status = 'processed'
                ORDER BY filename, id
                """
            )
            rows = await cur.fetchall()
            return [row[0] for row in rows]


async def resolve_search_document_ids(
    *,
    principal: Principal | None,
    upload_session_id: str,
    include_session_uploads: bool = False,
) -> list[int]:
    """Guests get only current-session uploads; authorized users get system
    documents and may additionally include their current-session uploads.
    """
    if principal is None:
        return await get_session_upload_ids(upload_session_id)

    if include_session_uploads:
        system_ids, upload_ids = await asyncio.gather(
            get_system_document_ids(principal),
            get_session_upload_ids(upload_session_id),
        )
        return list(dict.fromkeys(system_ids + upload_ids))

    return await get_system_document_ids(principal)


async def get_document_version_fingerprints(document_ids: list[int]) -> list[str]:
    """Return deterministic version stamps (id:content_hash:updated_at) for cache invalidation."""
    if not document_ids:
        return []

    async with await get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id, COALESCE(content_hash, ''), COALESCE(EXTRACT(EPOCH FROM updated_at)::text, '0')
                FROM public.documents
                WHERE id = ANY(%s)
                ORDER BY id
                """,
                (document_ids,),
            )
            rows = await cur.fetchall()
            return [f"{row[0]}:{row[1]}:{row[2]}" for row in rows]
