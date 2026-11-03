




"""Database utilities for managing RAG documents."""

from psycopg.types.json import Jsonb


VALID_STATUSES = {
    "pending",
    "processing",
    "processed",
    "failed",
}


def _validate_status(status):
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid document status: {status}")


def _get_file_metadata(file):
    return {
        "mime_type": file.get("mimeType"),
        "app_properties": file.get("appProperties", {}),
    }


def get_document(conn, drive_file_id):
    """Return an existing document using its Google Drive file ID."""

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                id,
                filename,
                content_hash,
                version,
                status
            FROM public.documents
            WHERE drive_file_id = %s
            """,
            (drive_file_id,),
        )

        return cur.fetchone()


def insert_document(
    conn,
    file,
    content_hash,
    folder_id,
    status="pending",
):
    """Insert a new document and its initial version."""

    _validate_status(status)

    metadata = Jsonb(_get_file_metadata(file))

    with conn.cursor() as cur:

        cur.execute(
            """
            INSERT INTO public.documents (
                filename,
                drive_file_id,
                drive_folder_id,
                content_hash,
                version,
                status,
                metadata
            )
            VALUES (%s, %s, %s, %s, 1, %s, %s)
            RETURNING id
            """,
            (
                file["name"],
                file["id"],
                folder_id,
                content_hash,
                status,
                metadata,
            ),
        )

        document_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO public.document_versions (
                document_id,
                version,
                filename,
                content_hash,
                metadata
            )
            VALUES (%s, 1, %s, %s, %s)
            """,
            (
                document_id,
                file["name"],
                content_hash,
                metadata,
            ),
        )

    return document_id


def update_document(
    conn,
    document,
    file,
    content_hash,
    folder_id=None,
    status="pending",
):
    """Update document information and register a new version."""

    _validate_status(status)

    document_id, _, _, old_version, _ = document
    new_version = old_version + 1

    metadata = Jsonb(_get_file_metadata(file))

    if folder_id is None:
        parents = file.get("parents", [])
        folder_id = parents[0] if parents else None

    with conn.cursor() as cur:

        cur.execute(
            """
            UPDATE public.documents
            SET
                filename = %s,
                drive_file_id = %s,
                drive_folder_id = COALESCE(%s, drive_folder_id),
                content_hash = %s,
                version = %s,
                status = %s,
                metadata = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            (
                file["name"],
                file["id"],
                folder_id,
                content_hash,
                new_version,
                status,
                metadata,
                document_id,
            ),
        )

        cur.execute(
            """
            INSERT INTO public.document_versions (
                document_id,
                version,
                filename,
                content_hash,
                metadata
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                document_id,
                new_version,
                file["name"],
                content_hash,
                metadata,
            ),
        )

    return document_id, new_version


def set_document_status(conn, document_id, status):
    """Update document processing status."""

    _validate_status(status)

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE public.documents
            SET
                status = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            (status, document_id),
        )


def document_has_complete_embeddings(conn, document_id):
    """Check whether all document chunks have embeddings."""

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                COUNT(*) AS total_chunks,
                COUNT(embedding) AS embedded_chunks
            FROM public.document_chunks
            WHERE document_id = %s
            """,
            (document_id,),
        )

        total_chunks, embedded_chunks = cur.fetchone()

    return total_chunks > 0 and total_chunks == embedded_chunks


def delete_document(conn, drive_file_id):
    """Delete a document using its Google Drive file ID."""

    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM public.documents
            WHERE drive_file_id = %s
            RETURNING filename
            """,
            (drive_file_id,),
        )

        result = cur.fetchone()

    return result[0] if result else None