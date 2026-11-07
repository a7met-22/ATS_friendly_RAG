

"""PDF parsing utilities powered by LlamaCloud."""

import io
from pathlib import Path
from typing import Any

from config.settings import (
    DATA_DIR,
    LLAMA_CLOUD_API_KEY,
)

from llama_cloud import LlamaCloud


DEFAULT_DATA_DIR = DATA_DIR


def create_client() -> LlamaCloud:
    """Create a LlamaCloud client."""

    if not LLAMA_CLOUD_API_KEY:
        raise RuntimeError(
            "LLAMA_CLOUD_API_KEY is missing from configuration."
        )

    return LlamaCloud(
        api_key=LLAMA_CLOUD_API_KEY,
        timeout=300.0,
        max_retries=2,
    )


def find_pdf_files(
    data_dir: str | Path = DEFAULT_DATA_DIR,
    recursive: bool = False,
) -> list[Path]:
    """Find local PDF files."""

    folder = Path(data_dir).expanduser()

    if not folder.is_dir():
        raise NotADirectoryError(
            f"PDF data directory does not exist: {folder}"
        )

    pattern = "**/*.pdf" if recursive else "*.pdf"

    pdf_files = sorted(folder.glob(pattern))

    if not pdf_files:
        print(f"No PDF files found in: {folder}")

    return pdf_files


def upload_pdf_files(
    client: LlamaCloud,
    data_dir: str | Path = DEFAULT_DATA_DIR,
    recursive: bool = False,
) -> list[Any]:
    """Upload discovered local PDFs."""

    uploaded_files = []

    for pdf_path in find_pdf_files(data_dir, recursive):

        print(f"Uploading: {pdf_path.name}")

        with pdf_path.open("rb") as pdf_file:

            uploaded_file = client.files.create(
                file=pdf_file,
                purpose="parse",
            )

        uploaded_files.append(uploaded_file)

        print(
            f"Uploaded successfully: {pdf_path.name} "
            f"(ID: {uploaded_file.id})"
        )

    return uploaded_files


def analyze_uploaded_files(
    client: LlamaCloud,
    uploaded_files: list[Any],
) -> dict[str, Any]:
    """Parse uploaded files."""

    results = {}

    for uploaded_file in uploaded_files:

        file_id = uploaded_file.id

        print(f"Parsing file ID: {file_id}")

        result = client.parsing.parse(
            file_id=file_id,
            tier="agentic",
            version="latest",
            expand=["markdown"],
        )

        results[file_id] = result

        print(f"Parsing completed for file ID: {file_id}")

    return results


def extract_pages_from_result(
    result: Any,
) -> list[dict[str, Any]]:
    """Extract successfully parsed pages."""

    markdown_data = getattr(
        result,
        "markdown",
        None,
    )

    pages = getattr(
        markdown_data,
        "pages",
        None,
    )

    if pages is None:
        raise ValueError(
            "The parsing result does not contain markdown pages."
        )

    extracted_pages = []

    for page in pages:

        if getattr(page, "success", False):

            extracted_pages.append(
                {
                    "page": getattr(
                        page,
                        "page_number",
                        None,
                    ),
                    "text": getattr(
                        page,
                        "markdown",
                        "",
                    ) or "",
                }
            )

        else:

            print(
                "Warning: parsing failed for page "
                f"{getattr(page, 'page_number', 'unknown')}"
            )

    return [
        page
        for page in extracted_pages
        if page["text"].strip()
    ]


def extract_text_from_parsed_result(
    result: Any,
) -> str:
    """Combine page Markdown into one text string."""

    pages = extract_pages_from_result(result)

    return "\n\n".join(
        page["text"]
        for page in pages
    )


def _parse_uploaded_file(
    client: LlamaCloud,
    file_object,
    filename: str,
) -> dict[str, Any]:
    """Parse an uploaded LlamaCloud file."""

    result = client.parsing.parse(
        file_id=file_object.id,
        tier="agentic",
        version="latest",
        expand=["markdown"],
    )

    pages = extract_pages_from_result(result)

    if not pages:
        raise ValueError(
            f"No pages were extracted from {filename}"
        )

    return {
        "file_name": filename,
        "pages": pages,
        "text": "\n\n".join(
            page["text"]
            for page in pages
        ),
    }


def parse_pdf_directory(
    data_dir: str | Path = DEFAULT_DATA_DIR,
    recursive: bool = False,
) -> dict[str, dict[str, Any]]:
    """Upload and parse all local PDFs."""

    client = create_client()

    uploaded_files = upload_pdf_files(
        client=client,
        data_dir=data_dir,
        recursive=recursive,
    )

    if not uploaded_files:
        return {}

    parsing_results = analyze_uploaded_files(
        client,
        uploaded_files,
    )

    output = {}

    for uploaded_file in uploaded_files:

        file_id = uploaded_file.id

        result = parsing_results[file_id]

        pages = extract_pages_from_result(result)

        output[file_id] = {
            "file_name": getattr(
                uploaded_file,
                "name",
                None,
            ),
            "uploaded_file": uploaded_file,
            "result": result,
            "pages": pages,
            "text": "\n\n".join(
                page["text"]
                for page in pages
            ),
        }

    return output


def parse_single_pdf(
    pdf_path: str | Path,
) -> dict[str, Any]:
    """Upload and parse one local PDF."""

    path = Path(pdf_path).expanduser().resolve()

    if (
        not path.is_file()
        or path.suffix.lower() != ".pdf"
    ):
        raise FileNotFoundError(
            f"PDF file not found: {path}"
        )

    client = create_client()

    print(f"Uploading: {path.name}")

    with path.open("rb") as pdf_file:

        uploaded_file = client.files.create(
            file=pdf_file,
            purpose="parse",
        )

    print(f"Parsing: {path.name}")

    return _parse_uploaded_file(
        client,
        uploaded_file,
        path.name,
    )


def parse_pdf_bytes(
    pdf_bytes: bytes,
    filename: str,
    client: LlamaCloud,
) -> dict[str, Any]:
    """Upload and parse a PDF received from Google Drive."""

    if not pdf_bytes:
        raise ValueError(
            f"PDF is empty: {filename}"
        )

    pdf_file = io.BytesIO(pdf_bytes)

    pdf_file.name = filename

    try:
        uploaded_file = client.files.create(
            file=pdf_file,
            purpose="parse",
        )

    except Exception as exc:
        response = getattr(exc, "response", None)

        status_code = getattr(exc, "status_code", None)

        response_text = (
            getattr(response, "text", None)
            if response is not None
            else None
        )

        request_id = (
            response.headers.get("x-request-id")
            if response is not None
            else None
        )

        raise RuntimeError(
            f"LlamaCloud upload failed: {filename}\n"
            f"File size: {len(pdf_bytes)} bytes\n"
            f"HTTP status: {status_code}\n"
            f"Request ID: {request_id}\n"
            f"Server response: {(response_text or str(exc))[:1500]}"
        ) from exc

    return _parse_uploaded_file(
        client,
        uploaded_file,
        filename,
    )


def create_drive_parser():
    """Create a parser compatible with document_processor and chunking."""

    client = create_client()

    def parse_from_drive(pdf_bytes, filename):

        parsed = parse_pdf_bytes(
            pdf_bytes,
            filename,
            client,
        )

        if not isinstance(parsed, dict):
            raise TypeError(
                "LlamaCloud parser must return a dictionary."
            )

        pages_data = parsed.get("pages")

        if not isinstance(pages_data, list):
            raise ValueError(
                f"No valid pages returned for {filename}."
            )

        # Convert every page to the format expected by chunking.py.
        pages = []

        for index, page in enumerate(pages_data, start=1):

            if isinstance(page, str):

                page_number = index
                page_text = page

            elif isinstance(page, dict):

                page_number = (
                    page.get("page")
                    or page.get("page_number")
                    or index
                )

                page_text = (
                    page.get("text")
                    or page.get("markdown")
                    or page.get("content")
                    or ""
                )

            else:
                continue

            if not isinstance(page_text, str):
                page_text = str(page_text)

            pages.append({
                "page": page_number,
                "text": page_text,
            })

        # Combine page contents.
        full_text = "\n\n".join(
            page["text"]
            for page in pages
            if page["text"].strip()
        )

        if not full_text.strip():
            raise ValueError(
                f"LlamaCloud extracted no readable text from {filename}."
            )

        return {
            "file_name": filename,
            "pages": pages,
            "text": full_text,
        }

    return parse_from_drive


if __name__ == "__main__":

    parsed_documents = parse_pdf_directory()

    if parsed_documents:

        print(
            f"\nSuccessfully parsed "
            f"{len(parsed_documents)} local PDF file(s)."
        )

        for file_id, document in parsed_documents.items():

            print(
                f"- {document['file_name'] or file_id}: "
                f"{len(document['pages'])} page(s), "
                f"{len(document['text'])} characters"
            )

    else:

        print("No local PDF documents were parsed.")