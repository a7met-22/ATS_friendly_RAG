



import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import io
from googleapiclient.http import MediaIoBaseDownload

from parsingWays.llama_parsing import create_drive_parser
from parsingWays.pymupdf_parsing import parse_pdf_bytes as pymupdf_parser

from config.settings import PARSER_TYPE

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CREDENTIALS_FILE = PROJECT_ROOT / "credentials.json"
TOKEN_FILE = PROJECT_ROOT / "token.json"
PARSING = PARSER_TYPE  # "llama" or "pymupdf"

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def connect_to_drive():
    """Authenticate the user and establish a Google Drive API connection."""

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
    )

    print("Google Drive connection successful!")

    return service


# Store Google Drive files
drive_files = []

# Store the target folder ID
resume_folder_id = None


def get_all_files(service, query):
    """Retrieve all files matching a Google Drive query."""

    files = []
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


def load_resume_docs(service):
    """Load existing files from resume_docs folder."""

    global drive_files, resume_folder_id

    # Find the target folder
    folders = get_all_files(
        service,
        "name = 'resume_docs' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )

    if not folders:
        raise FileNotFoundError("resume_docs folder was not found!")

    if len(folders) > 1:
        raise ValueError(
            "Multiple folders named resume_docs found. "
            "Please ensure there is only one."
        )

    resume_folder_id = folders[0]["id"]

    # Get files inside the folder
    current_files = get_all_files(
        service,
        f"'{resume_folder_id}' in parents and trashed = false"
    )

    # Prevent duplicates using file IDs
    drive_files = list({
        file["id"]: file
        for file in current_files
    }.values())

    if not drive_files:
        print("resume_docs folder is empty.")

    else:
        print(f"Loaded {len(drive_files)} files:")

        for file in drive_files:
            print(f"{file['name']} ({file['id']})")

    return drive_files


def process_new_file(file, service):

    print(f"Processing new file: {file['name']}")

    # Download PDF from Google Drive.
    request = service.files().get_media(
        fileId=file["id"]
    )

    file_buffer = io.BytesIO()

    downloader = MediaIoBaseDownload(
        file_buffer,
        request,
    )

    done = False

    while not done:
        _, done = downloader.next_chunk()

    pdf_bytes = file_buffer.getvalue()

    # Select the appropriate parser.
    if PARSING == "llama":
        parser = create_drive_parser()

    elif PARSING == "pymupdf":
        parser = pymupdf_parser

    else:
        raise ValueError(
            f"Unsupported parser: {PARSING}"
        )

    # Parse the downloaded PDF.
    parsed_document = parser(
        pdf_bytes,
        file["name"],
    )

    print(
        f"Parsing completed: {file['name']}"
    )

    return parsed_document

def track_folder_changes(service):
    """Detect newly added and deleted files."""

    global drive_files

    if not resume_folder_id:
        raise RuntimeError("Run load_resume_docs() first.")

    # Get the latest files from Google Drive
    current_files = get_all_files(
        service,
        f"'{resume_folder_id}' in parents and trashed = false"
    )

    # Create dictionaries for comparison
    old_files = {file["id"]: file for file in drive_files}
    new_files = {file["id"]: file for file in current_files}

    # Detect new files
    added_files = [
        file for file_id, file in new_files.items()
        if file_id not in old_files
    ]

    # Detect deleted files
    deleted_files = [
        file for file_id, file in old_files.items()
        if file_id not in new_files
    ]

    # Handle new files
    for file in added_files:

        print(f"NEW FILE DETECTED: {file['name']}")

        # Add to list
        drive_files.append(file)

        # Call parsing functions
        process_new_file(file, service)

    # Handle deleted files
    for deleted_file in deleted_files:

        print(f"FILE DELETED: {deleted_file['name']}")

        drive_files = [
            file for file in drive_files
            if file["id"] != deleted_file["id"]
        ]

    return drive_files


if __name__ == "__main__":

    service = connect_to_drive()

    load_resume_docs(service)

    track_folder_changes(service)

    print(
        "File tracking completed.",
        "Your files are:",
        [file["name"] for file in drive_files]
    )