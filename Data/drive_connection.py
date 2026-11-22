"""Async-compatible Google Drive connection, retrieval, and change tracking."""

from __future__ import annotations

import asyncio
import inspect
import io
import logging
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from config.settings import PARSER_TYPE
from parsingWays.llama_parsing import create_drive_parser
from parsingWays.pymupdf_parsing import parse_pdf_bytes as pymupdf_parser


logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CREDENTIALS_FILE = PROJECT_ROOT / "credentials.json"
TOKEN_FILE = PROJECT_ROOT / "token.json"
PARSING = PARSER_TYPE  # "llama" or "pymupdf"

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# قفل لحماية حالة المجلد والملفات من التداخل المتزامن (Race Conditions)
_drive_state_lock = asyncio.Lock()

# Store Google Drive files
drive_files: list[dict[str, Any]] = []

# Store the target folder ID
resume_folder_id: str | None = None


def _connect_to_drive_sync() -> Any:
    """Authenticate the user and build the Google Drive service synchronously."""
    credentials = None

    if TOKEN_FILE.exists():
        credentials = Credentials.from_authorized_user_file(
            str(TOKEN_FILE),
            SCOPES,
        )

    if not credentials or not credentials.valid:
        if (
            credentials
            and credentials.expired
            and credentials.refresh_token
        ):
            credentials.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                raise FileNotFoundError(
                    f"OAuth credentials not found: {CREDENTIALS_FILE}"
                )

            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE),
                SCOPES,
            )

            credentials = flow.run_local_server(port=0)

        TOKEN_FILE.write_text(credentials.to_json())

    service = build(
        "drive",
        "v3",
        credentials=credentials,
        cache_discovery=False,  # يمنع تحذيرات file_cache في بيئات الإنتاج
    )

    logger.info("Google Drive connection successful!")
    return service


async def connect_to_drive() -> Any:
    """Establish a Google Drive API connection without blocking the Event Loop."""
    return await asyncio.to_thread(_connect_to_drive_sync)


def _get_all_files_sync(service: Any, query: str) -> list[dict[str, Any]]:
    """Retrieve all files matching a Google Drive query synchronously."""
    files: list[dict[str, Any]] = []
    page_token = None

    while True:
        results = (
            service.files()
            .list(
                q=query,
                pageSize=100,
                pageToken=page_token,
                fields="nextPageToken, files(id, name, mimeType, modifiedTime)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )

        files.extend(results.get("files", []))
        page_token = results.get("nextPageToken")

        if not page_token:
            break

    return files


async def get_all_files(service: Any, query: str) -> list[dict[str, Any]]:
    """Retrieve all files matching a Google Drive query asynchronously."""
    return await asyncio.to_thread(_get_all_files_sync, service, query)


def _download_file_bytes_sync(service: Any, file_id: str) -> bytes:
    """Download file media bytes synchronously inside a worker thread."""
    request = service.files().get_media(fileId=file_id)
    file_buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(file_buffer, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    return file_buffer.getvalue()


async def load_resume_docs(service: Any) -> list[dict[str, Any]]:
    """Load existing files from resume_docs folder asynchronously."""
    global drive_files, resume_folder_id

    async with _drive_state_lock:
        folders = await get_all_files(
            service,
            "name = 'resume_docs' and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
        )

        if not folders:
            raise FileNotFoundError("resume_docs folder was not found!")

        if len(folders) > 1:
            raise ValueError(
                "Multiple folders named resume_docs found. "
                "Please ensure there is only one."
            )

        resume_folder_id = folders[0]["id"]

        current_files = await get_all_files(
            service,
            f"'{resume_folder_id}' in parents and trashed = false",
        )

        # Prevent duplicates using file IDs
        drive_files = list({
            file["id"]: file
            for file in current_files
        }.values())

        if not drive_files:
            logger.info("resume_docs folder is empty.")
        else:
            logger.info("Loaded %d files from resume_docs.", len(drive_files))
            for file in drive_files:
                logger.debug("Loaded file: %s (%s)", file["name"], file["id"])

        return drive_files


async def process_new_file(file: dict[str, Any], service: Any) -> dict[str, Any]:
    """Download and parse a single Google Drive PDF file asynchronously."""
    logger.info("Processing new file: %s", file["name"])

    # 1. Download PDF bytes in a background thread
    pdf_bytes = await asyncio.to_thread(
        _download_file_bytes_sync,
        service,
        file["id"],
    )

    # 2. Select the appropriate parser
    if PARSING == "llama":
        parser = create_drive_parser()
    elif PARSING == "pymupdf":
        parser = pymupdf_parser
    else:
        raise ValueError(f"Unsupported parser: {PARSING}")

    # 3. Parse the downloaded PDF (supports both async and sync parsers safely)
    parse_result = parser(pdf_bytes, file["name"])
    if inspect.isawaitable(parse_result):
        parsed_document = await parse_result
    else:
        parsed_document = parse_result

    logger.info("Parsing completed: %s", file["name"])
    return parsed_document


async def track_folder_changes(service: Any) -> list[dict[str, Any]]:
    """Detect newly added and deleted files asynchronously."""
    global drive_files

    async with _drive_state_lock:
        if not resume_folder_id:
            raise RuntimeError("Run load_resume_docs() first.")

        current_files = await get_all_files(
            service,
            f"'{resume_folder_id}' in parents and trashed = false",
        )

        old_files = {file["id"]: file for file in drive_files}
        new_files = {file["id"]: file for file in current_files}

        added_files = [
            file for file_id, file in new_files.items()
            if file_id not in old_files
        ]

        deleted_files = [
            file for file_id, file in old_files.items()
            if file_id not in new_files
        ]

        # معالجة الملفات المضافة بالتوازي المحكوم (بحد أقصى 3 ملفات معاً)
        if added_files:
            semaphore = asyncio.Semaphore(3)

            async def _handle_added(f: dict[str, Any]) -> dict[str, Any]:
                async with semaphore:
                    logger.info("NEW FILE DETECTED: %s", f["name"])
                    await process_new_file(f, service)
                    return f

            processed_added = await asyncio.gather(
                *[_handle_added(f) for f in added_files]
            )
            drive_files.extend(processed_added)

        for deleted_file in deleted_files:
            logger.info("FILE DELETED: %s", deleted_file["name"])
            drive_files = [
                file for file in drive_files
                if file["id"] != deleted_file["id"]
            ]

        return drive_files


async def _main() -> None:
    logging.basicConfig(level=logging.INFO)
    service = await connect_to_drive()
    await load_resume_docs(service)
    await track_folder_changes(service)
    print(
        "File tracking completed.",
        "Your files are:",
        [file["name"] for file in drive_files],
    )


if __name__ == "__main__":
    asyncio.run(_main())
