

"""Tests for the fixed-size chunking strategy."""

from langchain_text_splitters import python

from parsingWays.llama_parsing import parse_pdf_directory
from src.chunking import fixed_size_chunking


def main() -> None:
    print("Parsing PDF files...")

    documents = parse_pdf_directory()

    if not documents:
        print("FAIL: No PDF documents were parsed.")
        return

    # Select the first successfully parsed document.
    file_id, document = next(iter(documents.items()))

    print(f"\nDocument: {document['file_name'] or file_id}")
    print(f"Pages extracted: {len(document['pages'])}")
    print(f"Characters extracted: {len(document['text'])}")

    chunks = fixed_size_chunking(
        pages=document["pages"],
        chunk_size=500,
        overlap=75,
    )

    if not chunks:
        print("FAIL: No chunks were generated.")
        return

    print(f"\nChunks generated: {len(chunks)}")

    for chunk in chunks[:3]:
        print("\n" + "=" * 70)
        print(f"Chunk index: {chunk['chunk_index']}")
        print(f"Page: {chunk['metadata']['page']}")
        print(f"Characters: {len(chunk['content'])}")
        print("-" * 70)
        print(chunk["content"])

    print("\nPASS: Fixed-size chunking completed.")




def test_fixed_size_overlap() -> None:
    """Verify that consecutive chunks share the expected overlapping text."""
    sample_text = "ABCDEFGHIJKLMNOPQRSTUVWXYZ" * 40

    pages = [{"page": 1, "text": sample_text}]

    chunks = fixed_size_chunking(
        pages=pages,
        chunk_size=100,
        overlap=20,
    )

    if len(chunks) < 2:
        print("FAIL: At least two chunks are required to test overlap.")
        return

    first_chunk = chunks[0]["content"]
    second_chunk = chunks[1]["content"]

    expected_overlap = first_chunk[-20:]

    if second_chunk.startswith(expected_overlap):
        print("PASS: Consecutive chunks share the expected 20-character overlap.")
        print(f"Overlap: {expected_overlap}")
    else:
        print("FAIL: The expected overlap was not found.")
        print(f"Expected: {expected_overlap}")
        print(f"Actual beginning of second chunk: {second_chunk[:20]}")



if __name__ == "__main__":
    main()
    test_fixed_size_overlap()