"""Single entry point for Google Drive -> parsing -> chunking -> pgvector (Concurrent)."""

from __future__ import annotations

import asyncio
import hashlib
import io
from typing import Any

from googleapiclient.http import MediaIoBaseDownload

import Data.drive_connection as drive
from database_utilities.database_connection import (
    close_pool,
    get_connection,
    open_pool,
)
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

# أقصى عدد ملفات يتم تحميلها وتقطيعها وتضمينها بالتوازي في نفس اللحظة
MAX_CONCURRENT_FILES = 4


def download_file(service: Any, file_id: str) -> bytes:
    """Download one Google Drive file into memory (Sync)."""
    request = service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    file_bytes = buffer.getvalue()
    if not file_bytes:
        raise ValueError(
            f"Google Drive returned an empty file: {file_id}"
        )

    return file_bytes

# قفل لحماية كائن Google Drive service غير الآمن للخيوط المتعددة (Not Thread-Safe)
_drive_download_lock = asyncio.Lock()

async def download_file_async(service: Any, file_id: str) -> bytes:
    """Async wrapper to download a Google Drive file safely without OpenSSL thread collisions."""
    async with _drive_download_lock:
        return await asyncio.to_thread(download_file, service, file_id)


def _validate_drive_files(files: Any) -> list[dict[str, Any]]:
    """Validate the Google Drive file listing (Sync)."""
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


def _specialization_from_drive_file(
    file: dict[str, Any],
) -> str | None:
    """Read optional specialization from Google Drive appProperties (Sync)."""
    properties = file.get("appProperties") or {}
    value = properties.get("specialization")

    if isinstance(value, str) and value.strip():
        return value.strip()

    return None


# ------------------------------------------------------------
# 3. Failed Document Handling
# ------------------------------------------------------------

async def _register_failed_new_document(
    conn: Any,
    file: dict[str, Any],
    content_hash: str,
    folder_id: str,
) -> None:
    """Register a new file as failed so it can be retried."""
    async with conn.transaction():
        existing = await get_document(conn, file["id"])
        if existing is None:
            await insert_document(
                conn=conn,
                file=file,
                content_hash=content_hash,
                folder_id=folder_id,
                status="failed",
            )


async def _mark_existing_failed(
    conn: Any,
    document_id: int,
) -> None:
    """Persist failed processing status."""
    async with conn.transaction():
        await set_document_status(conn, document_id, "failed")


# ------------------------------------------------------------
# 4. Single Document Processing (Isolated Connection per Task)
# ------------------------------------------------------------

async def _process_one_file(
    service: Any,
    file: dict[str, Any],
    folder_id: str,
    parser: Any,
    stats: dict[str, int],
    stats_lock: asyncio.Lock,
) -> None:
    file_id = file["id"]
    filename = file["name"]

    existing = None
    content_hash = None

    try:
        # Step 1: Retrieve existing document status
        async with await get_connection() as conn:
            async with conn.transaction():
                existing = await get_document(conn, file_id)
                has_complete_embeddings = (
                    existing is not None
                    and await document_has_complete_embeddings(
                        conn,
                        existing[0],
                    )
                )

        # Step 2: Download and calculate SHA-256 (outside DB transaction)
        file_bytes = await download_file_async(service, file_id)
        content_hash = hashlib.sha256(file_bytes).hexdigest()

        # Step 3: Determine processing status
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
                async with stats_lock:
                    stats["unchanged"] += 1
                return

            is_update = (
                old_hash != content_hash
                or old_name != filename
            )

            if is_update:
                print(
                    f"MODIFIED FILE: {filename} "
                    f"(Version {old_version} -> {old_version + 1})"
                )
            else:
                print(
                    f"RETRYING: {filename} "
                    f"(Status: {old_status})"
                )

            async with await get_connection() as conn:
                async with conn.transaction():
                    await set_document_status(
                        conn,
                        document_id,
                        "processing",
                    )
        else:
            is_update = False
            print(f"NEW FILE: {filename}")

        # Step 4: Read specialization
        specialization = _specialization_from_drive_file(file)

        # Step 5: Parse PDF and generate chunks (outside DB transaction)
        processed = await process_pdf_bytes(
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

        # Step 6: Generate embeddings (outside DB transaction)
        vectors = await prepare_chunk_embeddings(
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

        # Step 7: Store document, chunks and embeddings (fast atomic DB write)
        async with await get_connection() as conn:
            async with conn.transaction():
                if existing is None:
                    document_id = await insert_document(
                        conn=conn,
                        file=file,
                        content_hash=content_hash,
                        folder_id=folder_id,
                        status="processing",
                    )
                elif is_update:
                    document_id, _new_version = await update_document(
                        conn=conn,
                        document=existing,
                        file=file,
                        content_hash=content_hash,
                        folder_id=folder_id,
                        status="processing",
                    )
                else:
                    document_id = existing[0]

                await store_chunks(
                    conn=conn,
                    document_id=document_id,
                    chunks=chunks,
                    embeddings=vectors,
                    specialization=specialization,
                    replace_existing=True,
                )

                await set_document_status(
                    conn,
                    document_id,
                    "processed",
                )

        # Step 8: Update statistics safely
        async with stats_lock:
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
        async with stats_lock:
            stats["failed"] += 1

        print(f"\nFAILED: {filename}")
        print(f"Reason: {type(exc).__name__}: {exc}")

        try:
            async with await get_connection() as conn:
                if existing is not None:
                    await _mark_existing_failed(conn, existing[0])
                elif content_hash is not None:
                    await _register_failed_new_document(
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


# ------------------------------------------------------------
# 5. Detect and Delete Missing Drive Documents
# ------------------------------------------------------------

async def _delete_missing_drive_documents(
    folder_id: str,
    current_file_ids: set[str],
    stats: dict[str, int],
) -> None:
    async with await get_connection() as conn:
        async with conn.transaction():
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT drive_file_id
                    FROM public.documents
                    WHERE drive_folder_id = %s
                      AND drive_file_id IS NOT NULL
                    """,
                    (folder_id,),
                )
                rows = await cur.fetchall()
                registered_ids = {row[0] for row in rows}

        deleted_ids = registered_ids - current_file_ids

        for file_id in deleted_ids:
            try:
                async with conn.transaction():
                    deleted_filename = await delete_document(
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


# ------------------------------------------------------------
# 6. Main Synchronization Pipeline
# ------------------------------------------------------------

async def sync_drive_documents(
    service: Any,
    parser: Any,
) -> dict[str, int]:
    """Synchronize Google Drive documents with PostgreSQL concurrently."""

    # Load Drive files asynchronously
    current_files = _validate_drive_files(
        await drive.load_resume_docs(service)
    )

    folder_id = drive.resume_folder_id
    if not folder_id:
        raise RuntimeError(
            "Google Drive resume folder ID was not resolved."
        )

    current_file_ids = {file["id"] for file in current_files}

    stats = {
        "inserted": 0,
        "updated": 0,
        "retried": 0,
        "deleted": 0,
        "unchanged": 0,
        "failed": 0,
    }
    stats_lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_FILES)

    async def _bounded_process(file: dict[str, Any]) -> None:
        async with semaphore:
            await _process_one_file(
                service=service,
                file=file,
                folder_id=folder_id,
                parser=parser,
                stats=stats,
                stats_lock=stats_lock,
            )

    # معالجة جميع الملفات بالتوازي المحكوم (4 ملفات في نفس اللحظة)
    if current_files:
        await asyncio.gather(
            *[_bounded_process(file) for file in current_files]
        )

    # Detect deleted files only when Drive returned files
    if current_files:
        await _delete_missing_drive_documents(
            folder_id=folder_id,
            current_file_ids=current_file_ids,
            stats=stats,
        )
    else:
        print(
            "WARNING: Google Drive returned no files. "
            "Skipping deletion to protect existing database records."
        )

    print("\n---------- SYNC SUMMARY ----------")
    print(f"Inserted:   {stats['inserted']}")
    print(f"Updated:    {stats['updated']}")
    print(f"Retried:    {stats['retried']}")
    print(f"Deleted:    {stats['deleted']}")
    print(f"Unchanged:  {stats['unchanged']}")
    print(f"Failed:     {stats['failed']}")
    print("Synchronization completed.")

    return stats


# ------------------------------------------------------------
# 7. Application Entry Point
# ------------------------------------------------------------

async def _run_sync_cli() -> None:
    await open_pool()
    try:
        drive_service = await drive.connect_to_drive()
        drive_parser = create_drive_parser()
        await sync_drive_documents(
            service=drive_service,
            parser=drive_parser,
        )
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(_run_sync_cli())
