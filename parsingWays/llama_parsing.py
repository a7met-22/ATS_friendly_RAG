"""Async PDF parsing utilities powered by LlamaCloud."""

import asyncio
import io
from pathlib import Path
from typing import Any

from config.settings import (
    DATA_DIR,
    LLAMA_CLOUD_API_KEY,
)
from llama_cloud import AsyncLlamaCloud


DEFAULT_DATA_DIR = DATA_DIR


def create_client() -> AsyncLlamaCloud:
    """Create an async LlamaCloud client."""
    if not LLAMA_CLOUD_API_KEY:
        raise RuntimeError(
            "LLAMA_CLOUD_API_KEY is missing from configuration."
        )

    return AsyncLlamaCloud(
        api_key=LLAMA_CLOUD_API_KEY,
        timeout=300.0,
        max_retries=2,
    )


def find_pdf_files(
    data_dir: str | Path = DEFAULT_DATA_DIR,
    recursive: bool = False,
) -> list[Path]:
    """Find local PDF files (Sync - Fast local directory scan)."""
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


async def _upload_single_file(
    client: AsyncLlamaCloud,
    pdf_path: Path,
) -> Any:
    """Helper to upload a single PDF file asynchronously."""
    print(f"Uploading: {pdf_path.name}")

    # قراءة بايتات الملف في Thread منفصل عشان منوقفش الـ Event Loop لو الملف كبير
    pdf_bytes = await asyncio.to_thread(pdf_path.read_bytes)
    pdf_file = io.BytesIO(pdf_bytes)
    pdf_file.name = pdf_path.name

    uploaded_file = await client.files.create(
        file=pdf_file,
        purpose="parse",
    )

    print(
        f"Uploaded successfully: {pdf_path.name} "
        f"(ID: {uploaded_file.id})"
    )
    return uploaded_file


async def upload_pdf_files(
    client: AsyncLlamaCloud,
    data_dir: str | Path = DEFAULT_DATA_DIR,
    recursive: bool = False,
) -> list[Any]:
    """Upload discovered local PDFs concurrently."""
    pdf_paths = find_pdf_files(data_dir, recursive)
    if not pdf_paths:
        return []

    # رفع كل الملفات في نفس الوقت بالتوازي بدل واحد تلو الآخر
    tasks = [_upload_single_file(client, path) for path in pdf_paths]
    return await asyncio.gather(*tasks)


async def _analyze_single_file(
    client: AsyncLlamaCloud,
    uploaded_file: Any,
) -> tuple[str, Any]:
    """Helper to parse a single uploaded file asynchronously."""
    file_id = uploaded_file.id
    print(f"Parsing file ID: {file_id}")

    result = await client.parsing.parse(
        file_id=file_id,
        tier="agentic",
        version="latest",
        expand=["markdown"],
    )

    print(f"Parsing completed for file ID: {file_id}")
    return file_id, result


async def analyze_uploaded_files(
    client: AsyncLlamaCloud,
    uploaded_files: list[Any],
) -> dict[str, Any]:
    """Parse uploaded files concurrently."""
    if not uploaded_files:
        return {}

    # تحليل كل الملفات المرفوعة بالتوازي في نفس اللحظة
    tasks = [_analyze_single_file(client, file) for file in uploaded_files]
    results_list = await asyncio.gather(*tasks)
    
    return dict(results_list)


def extract_pages_from_result(
    result: Any,
) -> list[dict[str, Any]]:
    """Extract successfully parsed pages (Sync - Pure CPU memory operation)."""
    markdown_data = getattr(result, "markdown", None)
    pages = getattr(markdown_data, "pages", None)

    if pages is None:
        raise ValueError(
            "The parsing result does not contain markdown pages."
        )

    extracted_pages = []
    for page in pages:
        if getattr(page, "success", False):
            extracted_pages.append(
                {
                    "page": getattr(page, "page_number", None),
                    "text": getattr(page, "markdown", "") or "",
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
    """Combine page Markdown into one text string (Sync)."""
    pages = extract_pages_from_result(result)
    return "\n\n".join(page["text"] for page in pages)


async def _parse_uploaded_file(
    client: AsyncLlamaCloud,
    file_object: Any,
    filename: str,
) -> dict[str, Any]:
    """Parse an uploaded LlamaCloud file asynchronously."""
    result = await client.parsing.parse(
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
        "text": "\n\n".join(page["text"] for page in pages),
    }


async def parse_pdf_directory(
    data_dir: str | Path = DEFAULT_DATA_DIR,
    recursive: bool = False,
) -> dict[str, dict[str, Any]]:
    """Upload and parse all local PDFs concurrently."""
    client = create_client()

    uploaded_files = await upload_pdf_files(
        client=client,
        data_dir=data_dir,
        recursive=recursive,
    )

    if not uploaded_files:
        return {}

    parsing_results = await analyze_uploaded_files(
        client,
        uploaded_files,
    )

    output = {}
    for uploaded_file in uploaded_files:
        file_id = uploaded_file.id
        result = parsing_results[file_id]
        pages = extract_pages_from_result(result)

        output[file_id] = {
            "file_name": getattr(uploaded_file, "name", None),
            "uploaded_file": uploaded_file,
            "result": result,
            "pages": pages,
            "text": "\n\n".join(page["text"] for page in pages),
        }

    return output


async def parse_single_pdf(
    pdf_path: str | Path,
) -> dict[str, Any]:
    """Upload and parse one local PDF asynchronously."""
    path = Path(pdf_path).expanduser().resolve()

    if not path.is_file() or path.suffix.lower() != ".pdf":
        raise FileNotFoundError(f"PDF file not found: {path}")

    client = create_client()
    uploaded_file = await _upload_single_file(client, path)

    print(f"Parsing: {path.name}")
    return await _parse_uploaded_file(
        client,
        uploaded_file,
        path.name,
    )


async def parse_pdf_bytes(
    pdf_bytes: bytes,
    filename: str,
    client: AsyncLlamaCloud,
) -> dict[str, Any]:
    """Upload and parse a PDF received from Google Drive asynchronously."""
    if not pdf_bytes:
        raise ValueError(f"PDF is empty: {filename}")

    pdf_file = io.BytesIO(pdf_bytes)
    pdf_file.name = filename

    try:
        uploaded_file = await client.files.create(
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

    return await _parse_uploaded_file(
        client,
        uploaded_file,
        filename,
    )


def create_drive_parser():
    """Create an async parser compatible with document_processor and chunking."""
    client = create_client()

    async def parse_from_drive(pdf_bytes: bytes, filename: str) -> dict[str, Any]:
        parsed = await parse_pdf_bytes(
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
                f"No valid pages returned for {filename}"
            )
        
        return parsed

    return parse_from_drive
