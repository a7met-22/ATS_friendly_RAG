"""Resolve and enforce the document scope available to a user."""

from __future__ import annotations

from database_utilities.database_connection import get_connection
from security.authorization import (
    PERMISSION_SYSTEM_SEARCH,
    Principal,
    require_permission,
)


def get_session_upload_ids(upload_session_id: str) -> list[int]:
    if not upload_session_id:
        return []
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM public.documents
                WHERE drive_file_id IS NULL
                  AND status = 'processed'
                  AND metadata->>'source_type' = 'streamlit_upload'
                  AND metadata->>'upload_session_id' = %s
                ORDER BY created_at, id
                """,
                (upload_session_id,),
            )
            return [row[0] for row in cur.fetchall()]


def get_system_document_ids(principal: Principal | None) -> list[int]:
    require_permission(principal, PERMISSION_SYSTEM_SEARCH)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM public.documents
                WHERE drive_file_id IS NOT NULL
                  AND status = 'processed'
                ORDER BY filename, id
                """
            )
            return [row[0] for row in cur.fetchall()]


def resolve_search_document_ids(
    *,
    principal: Principal | None,
    upload_session_id: str,
    include_session_uploads: bool = False,
) -> list[int]:
    """Guests get only current-session uploads; authorized users get system
    documents and may additionally include their current-session uploads.
    """
    if principal is None:
        return get_session_upload_ids(upload_session_id)

    # Re-check permission at the service boundary, not only in the UI.
    system_ids = get_system_document_ids(principal)
    if include_session_uploads:
        upload_ids = get_session_upload_ids(upload_session_id)
        return list(dict.fromkeys(system_ids + upload_ids))
    return system_ids
