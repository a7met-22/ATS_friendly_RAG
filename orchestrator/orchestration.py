




"""Single entry point for Google Drive -> parsing -> chunking -> pgvector."""

from __future__ import annotations

import hashlib
import io
from typing import Any

from googleapiclient.http import MediaIoBaseDownload

import Data.drive_connection as drive

from database_utilities.database_connection import get_connection

from database_utilities.document_utilities import (
    delete_document,
    document_has_complete_embeddings,
    get_document,
    insert_document,
    set_document_status,
    update_document,
)

from parsingWays.llama_parsing import create_drive_parser

from src.document_processor import process_pdf_bytes

from src.store_chunks import (
    prepare_chunk_embeddings,
    store_chunks,
)


# ============================================================
# 1. Google Drive Download
# ============================================================

def download_file(service: Any, file_id: str) -> bytes:
    """Download one Google Drive file into memory."""

    request = service.files().get_media(
        fileId=file_id
    )

    buffer = io.BytesIO()

    downloader = MediaIoBaseDownload(
        buffer,
        request,
    )

    done = False

    while not done:
        _, done = downloader.next_chunk()

    file_bytes = buffer.getvalue()

    if not file_bytes:
        raise ValueError(
            f"Google Drive returned an empty file: {file_id}"
        )

    return file_bytes


def _validate_drive_files(files: Any) -> list[dict[str, Any]]:
    """Validate the Google Drive file listing."""

    if files is None:
        raise RuntimeError(
            "Google Drive returned None instead of a file list."
        )

    if not isinstance(files, list):
        files = list(files)

    seen_ids: set[str] = set()
    validated: list[dict[str, Any]] = []

    for index, file in enumerate(files):

        if not isinstance(file, dict):
            raise TypeError(
                f"Drive item #{index} is not a dictionary."
            )

        file_id = file.get("id")
        filename = file.get("name")

        if not isinstance(file_id, str) or not file_id:
            raise ValueError(
                f"Drive item #{index} has no valid file ID."
            )

        if not isinstance(filename, str) or not filename.strip():
            raise ValueError(
                f"Drive file {file_id} has no valid filename."
            )

        if file_id in seen_ids:
            raise ValueError(
                f"Duplicate Google Drive file ID: {file_id}"
            )

        seen_ids.add(file_id)
        validated.append(file)

    return validated


# ============================================================
# 2. Document Metadata
# ============================================================

def _specialization_from_drive_file(
    file: dict[str, Any],
) -> str | None:
    """Read optional specialization from Google Drive appProperties."""

    properties = file.get("appProperties") or {}

    value = properties.get("specialization")

    if isinstance(value, str) and value.strip():
        return value.strip()

    return None


# ============================================================
# 3. Failed Document Handling
# ============================================================

def _register_failed_new_document(
    conn: Any,
    file: dict[str, Any],
    content_hash: str,
    folder_id: str,
) -> None:
    """Register a new file as failed so it can be retried."""

    with conn.transaction():

        existing = get_document(
            conn,
            file["id"],
        )

        if existing is None:

            insert_document(
                conn=conn,
                file=file,
                content_hash=content_hash,
                folder_id=folder_id,
                status="failed",
            )


def _mark_existing_failed(
    conn: Any,
    document_id: int,
) -> None:
    """Persist failed processing status."""

    with conn.transaction():

        set_document_status(
            conn,
            document_id,
            "failed",
        )


# ============================================================
# 4. Process One Document
# ============================================================

def _process_one_file(
    conn: Any,
    service: Any,
    file: dict[str, Any],
    folder_id: str,
    parser: Any,
    stats: dict[str, int],
) -> None:

    file_id = file["id"]
    filename = file["name"]

    existing = None
    content_hash = None

    try:

        # ----------------------------------------------------
        # Step 1: Retrieve existing document
        # ----------------------------------------------------

        with conn.transaction():

            existing = get_document(
                conn,
                file_id,
            )

            has_complete_embeddings = (
                existing is not None
                and document_has_complete_embeddings(
                    conn,
                    existing[0],
                )
            )

        # ----------------------------------------------------
        # Step 2: Download and calculate SHA-256
        # ----------------------------------------------------

        file_bytes = download_file(
            service,
            file_id,
        )

        content_hash = hashlib.sha256(
            file_bytes
        ).hexdigest()

        # ----------------------------------------------------
        # Step 3: Determine processing status
        # ----------------------------------------------------

        if existing is not None:

            (
                document_id,
                old_name,
                old_hash,
                old_version,
                old_status,
            ) = existing

            is_unchanged = (
                old_hash == content_hash
                and old_name == filename
                and old_status == "processed"
                and has_complete_embeddings
            )

            if is_unchanged:

                print(
                    f"UNCHANGED: {filename} "
                    f"(Version {old_version})"
                )

                stats["unchanged"] += 1
                return

            is_update = (
                old_hash != content_hash
                or old_name != filename
            )

            if is_update:

                print(
                    f"MODIFIED FILE: {filename} "
                    f"(Version {old_version} "
                    f"-> {old_version + 1})"
                )

            else:

                print(
                    f"RETRYING: {filename} "
                    f"(Status: {old_status})"
                )

            # Mark existing document as processing.
            with conn.transaction():

                set_document_status(
                    conn,
                    document_id,
                    "processing",
                )

        else:

            is_update = False

            print(f"NEW FILE: {filename}")

        # ----------------------------------------------------
        # Step 4: Read specialization
        # ----------------------------------------------------

        specialization = (
            _specialization_from_drive_file(file)
        )

        # ----------------------------------------------------
        # Step 5: Parse PDF and generate chunks
        # ----------------------------------------------------

        processed = process_pdf_bytes(
            pdf_bytes=file_bytes,
            filename=filename,
            parser=parser,
            specialization=specialization,
        )

        if not isinstance(processed, dict):
            raise TypeError(
                "process_pdf_bytes() must return a dictionary."
            )

        chunks = processed.get("chunks")

        if not isinstance(chunks, list) or not chunks:
            raise ValueError(
                f"No chunks were produced for {filename}."
            )

        # ----------------------------------------------------
        # Step 6: Generate embeddings
        # ----------------------------------------------------

        vectors = prepare_chunk_embeddings(
            document_name=filename,
            chunks=chunks,
            specialization=specialization,
        )

        if vectors is None or len(vectors) != len(chunks):

            raise ValueError(
                f"Embedding count does not match chunk count "
                f"for {filename}: "
                f"{0 if vectors is None else len(vectors)} "
                f"embeddings, {len(chunks)} chunks."
            )

        # ----------------------------------------------------
        # Step 7: Store document, chunks and embeddings
        # ----------------------------------------------------

        with conn.transaction():

            if existing is None:

                document_id = insert_document(
                    conn=conn,
                    file=file,
                    content_hash=content_hash,
                    folder_id=folder_id,
                    status="processing",
                )

            elif is_update:

                document_id, _new_version = update_document(
                    conn=conn,
                    document=existing,
                    file=file,
                    content_hash=content_hash,
                    folder_id=folder_id,
                    status="processing",
                )

            else:

                document_id = existing[0]

            # Store chunks and embeddings.
            store_chunks(
                conn=conn,
                document_id=document_id,
                chunks=chunks,
                embeddings=vectors,
                specialization=specialization,
                replace_existing=True,
            )

            # Mark document as successfully processed.
            set_document_status(
                conn,
                document_id,
                "processed",
            )

        # ----------------------------------------------------
        # Step 8: Update statistics
        # ----------------------------------------------------

        if existing is None:

            stats["inserted"] += 1

        elif is_update:

            stats["updated"] += 1

        else:

            stats["retried"] += 1

        print(
            f"PROCESSED: {filename} | "
            f"Chunks: {len(chunks)}"
        )

    except Exception as exc:

        stats["failed"] += 1

        print(f"\nFAILED: {filename}")

        print(
            f"Reason: {type(exc).__name__}: {exc}"
        )

        # Preserve the previous committed chunks/version
        # if processing an existing document fails.
        try:

            if existing is not None:

                _mark_existing_failed(
                    conn,
                    existing[0],
                )

            elif content_hash is not None:

                _register_failed_new_document(
                    conn=conn,
                    file=file,
                    content_hash=content_hash,
                    folder_id=folder_id,
                )

        except Exception as status_exc:

            print(
                "Could not persist failed status: "
                f"{type(status_exc).__name__}: {status_exc}"
            )


# ============================================================
# 5. Detect and Delete Missing Drive Documents
# ============================================================

def _delete_missing_drive_documents(
    conn: Any,
    folder_id: str,
    current_file_ids: set[str],
    stats: dict[str, int],
) -> None:

    with conn.transaction():

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT drive_file_id
                FROM public.documents
                WHERE drive_folder_id = %s
                  AND drive_file_id IS NOT NULL
                """,
                (folder_id,),
            )

            registered_ids = {
                row[0]
                for row in cur.fetchall()
            }

    deleted_ids = registered_ids - current_file_ids

    for file_id in deleted_ids:

        try:

            with conn.transaction():

                deleted_filename = delete_document(
                    conn,
                    file_id,
                )

            if deleted_filename:

                stats["deleted"] += 1

                print(
                    f"DELETED: {deleted_filename} "
                    f"(Drive ID: {file_id})"
                )

        except Exception as exc:

            stats["failed"] += 1

            print(
                f"FAILED TO DELETE Drive file {file_id}: "
                f"{type(exc).__name__}: {exc}"
            )


# ============================================================
# 6. Main Synchronization Function
# ============================================================

def sync_drive_documents(
    service: Any,
    parser: Any,
) -> dict[str, int]:
    """Synchronize Google Drive documents with PostgreSQL.

    Downloading, parsing and embedding run outside transactions.
    Each document's database changes are committed independently.
    """

    # Load Drive files first.
    current_files = _validate_drive_files(
        drive.load_resume_docs(service)
     )

    # Read the folder ID after loading the files.
    folder_id = drive.resume_folder_id

    if not folder_id:
        raise RuntimeError(
            "Google Drive resume folder ID was not resolved."
        )

    current_file_ids = {
        file["id"]
        for file in current_files
    }

    stats = {
        "inserted": 0,
        "updated": 0,
        "retried": 0,
        "deleted": 0,
        "unchanged": 0,
        "failed": 0,
    }

    conn = get_connection()

    try:

        # Process each current Drive file independently.
        for file in current_files:

            _process_one_file(
                conn=conn,
                service=service,
                file=file,
                folder_id=folder_id,
                parser=parser,
                stats=stats,
            )

        # Detect deleted files only when Drive returned files.
        # This protects existing records from an unexpected empty listing.
        if current_files:

            _delete_missing_drive_documents(
                conn=conn,
                folder_id=folder_id,
                current_file_ids=current_file_ids,
                stats=stats,
            )

        else:

            print(
                "WARNING: Google Drive returned no files. "
                "Skipping deletion to protect existing database records."
            )

    finally:

        conn.close()

    # --------------------------------------------------------
    # Synchronization Summary
    # --------------------------------------------------------

    print("\n========== SYNC SUMMARY ==========")

    print(f"Inserted:   {stats['inserted']}")
    print(f"Updated:    {stats['updated']}")
    print(f"Retried:    {stats['retried']}")
    print(f"Deleted:    {stats['deleted']}")
    print(f"Unchanged:  {stats['unchanged']}")
    print(f"Failed:     {stats['failed']}")

    print("Synchronization completed.")

    return stats


# ============================================================
# 7. Application Entry Point
# ============================================================

if __name__ == "__main__":

    # Connect to Google Drive.
    drive_service = drive.connect_to_drive()

    # Create one reusable LlamaCloud parser.
    drive_parser = create_drive_parser()

    # Start synchronization.
    sync_drive_documents(
        service=drive_service,
        parser=drive_parser,
    )