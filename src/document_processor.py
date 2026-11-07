




"""Parse one PDF and apply section-based chunking."""

from typing import Any, Callable

from src.chunking import section_based_chunking


CHUNK_SIZE = 500

CHUNK_OVERLAP = 75


def process_pdf_bytes(
    pdf_bytes: bytes,
    filename: str,
    parser: Callable[[bytes, str], dict[str, Any]],
    specialization: str | None = None,
) -> dict[str, Any]:
    """Parse PDF bytes and generate section-based chunks."""

    if not pdf_bytes:
        raise ValueError(
            f"PDF is empty: {filename}"
        )

    if not filename.lower().endswith(".pdf"):
        raise ValueError(
            f"Only PDF files are supported: {filename}"
        )

    # Step 1: Parse PDF into pages.
    parsed_document = parser(
        pdf_bytes,
        filename,
    )

    pages = parsed_document.get("pages")

    if (
        not isinstance(pages, list)
        or not pages
    ):
        raise ValueError(
            f"Parser returned no pages for {filename}"
        )

    # Step 2: Apply the existing section-based strategy.
    chunks = section_based_chunking(
        pages,
        chunk_size=CHUNK_SIZE,
        overlap=CHUNK_OVERLAP,
    )

    if not chunks:
        raise ValueError(
            f"No chunks were generated for {filename}"
        )

    # Step 3: Add missing metadata .
    for chunk in chunks:

        metadata = chunk.setdefault(
            "metadata",
            {},
        )

        metadata.setdefault(
            "source",
            filename,
        )

        if specialization and not metadata.get("specialization"):
            metadata["specialization"] = specialization

    return {
        "file_name": filename,
        "pages": pages,
        "text": parsed_document.get("text", ""),
        "chunks": chunks,
        "specialization": specialization,
    }