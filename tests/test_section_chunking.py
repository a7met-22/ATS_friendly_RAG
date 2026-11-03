
from src.chunking import section_based_chunking

pages = [
    {
        "page": 1,
        "text": (
            "## Summary\nMachine Learning Engineer.\n\n"
            "## Skills\nPython, SQL, Docker.\n\n"
            "## Experience\nBuilt ML models."
        ),
    }
]

chunks = section_based_chunking(pages, chunk_size=100, overlap=20)

for chunk in chunks:
    print(
        f"\nSection: {chunk['metadata']['section']}"
        f"\nChunk: {chunk['chunk_index']}"
        f"\n{chunk['content']}"
    )

assert chunks, "No chunks generated."
assert all(chunk["metadata"].get("section") for chunk in chunks)

print("\nPASS: Section-based chunking completed.")
