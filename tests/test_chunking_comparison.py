


"""Compare fixed-size and recursive chunking on the same input."""

from src.chunking import fixed_size_chunking, recursive_chunking


def main() -> None:
    sample_pages = [
        {
            "page": 1,
            "text": (
                "## Professional Summary\n\n"
                "Machine Learning Engineer with experience building models.\n\n"
                "## Skills\n\n"
                "Python, SQL, scikit-learn, XGBoost, Docker.\n\n"
                "## Experience\n\n"
                "Developed machine learning models for business forecasting."
            ),
        }
    ]

    strategies = {
        "Fixed-Size": fixed_size_chunking,
        "Recursive": recursive_chunking,
    }

    for strategy_name, strategy_function in strategies.items():
        chunks = strategy_function(
            pages=sample_pages,
            chunk_size=100,
            overlap=20,
        )

        print(f"\n{'=' * 60}")
        print(f"Strategy: {strategy_name}")
        print(f"Chunks generated: {len(chunks)}")

        for chunk in chunks:
            print(f"\nChunk {chunk['chunk_index']}")
            print(f"Characters: {len(chunk['content'])}")
            print("-" * 40)
            print(chunk["content"])

    print("\nPASS: Both strategies completed without errors.")


if __name__ == "__main__":
    main()
