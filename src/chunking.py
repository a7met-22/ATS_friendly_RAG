


from typing import Any



"""Recursive chunking utilities for the RAG document pipeline."""

from typing import Any
from langchain_text_splitters import RecursiveCharacterTextSplitter


def recursive_chunking(
    pages: list[dict[str, Any]],
    chunk_size: int = 500,
    overlap: int = 75,
) -> list[dict[str, Any]]:
    """
    Split page-level text using recursive separators.

    Each generated chunk retains its source page number.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero.")

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError(
            "Overlap must be non-negative and smaller than chunk_size."
        )

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        length_function=len,
        separators=["\n\n", "\n", " ", ""],
        strip_whitespace=True,
    )

    chunks: list[dict[str, Any]] = []

    for page_data in pages:
        page_number = page_data.get("page")
        text = page_data.get("text", "")

        if not isinstance(text, str):
            raise TypeError("Each page's text must be a string.")

        if not text.strip():
            continue

        page_chunks = splitter.split_text(text)

        for content in page_chunks:
            chunks.append(
                {
                    "chunk_index": len(chunks),
                    "content": content,
                    "token_count": None,
                    "metadata": {
                        "page": page_number,
                        "chunking_strategy": "recursive",
                        "chunk_size": chunk_size,
                        "overlap": overlap,
                    },
                }
            )

    return chunks





"""Section-based chunking for resume documents."""

import re
from typing import Any


def extract_cv_owner_name(full_text: str) -> str | None:
    """Extract a possible CV owner's name from the beginning of the CV."""

    section_pattern = re.compile(
        r"(?im)^\s{0,3}#{0,3}\s*"
        r"(professional summary|summary|skills|technical skills|"
        r"experience|work experience|education|projects|certifications|"
        r"awards|publications|interests|languages)\s*:?\s*$"
    )

    first_section = section_pattern.search(full_text)
    header_text = (
        full_text[:first_section.start()]
        if first_section
        else full_text[:1000]
    )

    for line in header_text.splitlines():
        candidate = line.strip()

        if not candidate:
            continue

        # Skip contact details, URLs, and common labels.
        if re.search(
            r"@|https?://|www\.|linkedin|github|"
            r"\+?\d[\d\s()\-]{7,}",
            candidate,
            re.IGNORECASE,
        ):
            continue

        if re.search(
            r"(?i)\b(curriculum vitae|resume|cv|"
            r"email|phone|mobile|address|professional summary)\b",
            candidate,
        ):
            continue

        # A name candidate should contain alphabetic characters
        # and normally consist of 2-5 words.
        words = candidate.split()

        if (
            2 <= len(words) <= 5
            and re.fullmatch(
                r"[A-Za-z][A-Za-z.'’-]*(?:\s+[A-Za-z][A-Za-z.'’-]*){1,4}",
                candidate,
            )
        ):
            return candidate

    return None


def section_based_chunking(
    pages: list[dict[str, Any]],
    chunk_size: int = 500,
    overlap: int = 75,
) -> list[dict[str, Any]]:
    """Detect CV sections, calculate statistics, and attach metadata."""

    # 1. Collect the complete text.
    full_text = "\n".join(
        page["text"]
        for page in pages
        if page.get("text", "").strip()
    )

    if not full_text.strip():
        return []

    # 2. Detect section headings.
    section_pattern = re.compile(
        r"(?im)^\s{0,3}#{0,3}\s*"
        r"(professional summary|summary|skills|technical skills|"
        r"experience|work experience|education|projects|certifications|"
        r"awards|publications|interests|languages)\s*:?\s*$"
    )

    matches = list(section_pattern.finditer(full_text))

    # 3. Extract a possible CV owner's name.
    cv_owner_name = extract_cv_owner_name(full_text)

    # If no headings exist, process the entire text as one section.
    sections = []

    if not matches:
        sections.append(("General", full_text.strip()))
    else:
        if full_text[:matches[0].start()].strip():
            sections.append(
                ("General", full_text[:matches[0].start()].strip())
            )

        for index, match in enumerate(matches):
            end = (
                matches[index + 1].start()
                if index + 1 < len(matches)
                else len(full_text)
            )

            section_text = full_text[match.start():end].strip()
            section_name = match.group(1).title()

            sections.append((section_name, section_text))

    chunks = []
    section_statistics = []

    # 4. Process each section independently.
    for section_name, section_text in sections:
        word_count = len(section_text.split())

        section_chunks = recursive_chunking(
            pages=[{"page": None, "text": section_text}],
            chunk_size=chunk_size,
            overlap=overlap,
        )

        # Number of chunks actually generated for this section.
        chunk_count = len(section_chunks)

        section_statistics.append({
            "section": section_name,
            "word_count": word_count,
            "chunk_count": chunk_count,
        })

        # 5. Attach section and document metadata to every chunk.
        for chunk in section_chunks:
            chunk["chunk_index"] = len(chunks)

            chunk.setdefault("metadata", {})
            chunk["metadata"].update({
                "chunking_strategy": "section_based",
                "section": section_name,
                "section_word_count": word_count,
                "section_chunk_count": chunk_count,
                "cv_owner_name": cv_owner_name,
            })

            chunks.append(chunk)

    return chunks