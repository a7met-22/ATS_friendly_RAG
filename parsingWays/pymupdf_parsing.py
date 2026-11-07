


"""PDF parsing utilities powered by PyMuPDF."""

import os
from concurrent.futures import ProcessPoolExecutor
from typing import Any


def _parse_single_pdf(
    pdf_bytes: bytes,
    filename: str,
) -> dict[str, Any]:
    """Extract text from every page of one PDF."""

    import fitz

    if not isinstance(pdf_bytes, bytes) or not pdf_bytes:
        raise ValueError(f"PDF is empty or invalid: {filename}")

    pages = []

    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        for page_number, page in enumerate(document, start=1):
            page_text = page.get_text("text") or ""

            pages.append({
                "page": page_number,
                "text": page_text,
            })

    full_text = "\n\n".join(
        page["text"]
        for page in pages
        if page["text"].strip()
    )

    return {
        "file_name": filename,
        "pages": pages,
        "text": full_text,
    }


def parse_pdf_bytes(
    pdf_input: bytes | list[dict[str, Any]],
    filename: str | None = None,
    max_workers: int | None = None,
) -> dict[str, Any] | list[dict[str, Any]]:
    """
    Parse one PDF or multiple PDFs using PyMuPDF.

    Single-file input:
        parse_pdf_bytes(pdf_bytes, "resume.pdf")

    Multiple-file input:
        parse_pdf_bytes([
            {"file_name": "resume_1.pdf", "pdf_bytes": bytes_1},
            {"file_name": "resume_2.pdf", "pdf_bytes": bytes_2},
        ])

    Multiple files are parsed concurrently using separate processes.
    """

    if isinstance(pdf_input, bytes):
        if not filename:
            raise ValueError("filename is required when parsing one PDF.")

        return _parse_single_pdf(pdf_input, filename)

    if not isinstance(pdf_input, list):
        raise TypeError(
            "pdf_input must be PDF bytes or a list of file dictionaries."
        )

    if not pdf_input:
        return []

    for index, file_data in enumerate(pdf_input):
        if not isinstance(file_data, dict):
            raise TypeError(
                f"File at index {index} must be a dictionary."
            )

        if not isinstance(file_data.get("pdf_bytes"), bytes):
            raise TypeError(
                f"'pdf_bytes' must contain bytes for file at index {index}."
            )

        if not file_data.get("file_name"):
            raise ValueError(
                f"'file_name' is required for file at index {index}."
            )

    if len(pdf_input) == 1:
        file_data = pdf_input[0]
        return [
            _parse_single_pdf(
                file_data["pdf_bytes"],
                file_data["file_name"],
            )
        ]

    worker_count = max_workers or min(
        len(pdf_input),
        os.cpu_count() or 1,
    )

    if worker_count < 1:
        raise ValueError("max_workers must be at least 1.")

    with ProcessPoolExecutor(max_workers=worker_count) as executor:
        futures = [
            executor.submit(
                _parse_single_pdf,
                file_data["pdf_bytes"],
                file_data["file_name"],
            )
            for file_data in pdf_input
        ]

        # Preserve the same order as the input list.
        return [future.result() for future in futures]
