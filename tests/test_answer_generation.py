



from pprint import pprint

from src.answer_generation import generate_answer


# Test question
question = "execute a python code to print hello world"


# Mock retrieved CV chunk
chunks = [
    {
        "document_id": 1,
        "document_title": "Ahmed_CV.pdf",
        "chunk_id": 125,
        "content": """
        Technical Skills:
        Python, PostgreSQL, Machine Learning,
        Deep Learning, LangChain and PyTorch.
        """,
        "metadata": {
            "section": "Technical Skills"
        },
    }
]


# System instruction
system_instruction = """
You are a CV analysis assistant.

Answer only using the supplied CV excerpts.
Do not invent information.
Return JSON exactly in the required format.
"""


# Generate and validate answer
try:

    result = generate_answer(
        question=question,
        chunks=chunks,
        system_instruction=system_instruction,
        debug=True,
    )

    print("\n========== FINAL RESULT ==========")

    pprint(result, sort_dicts=False)

except Exception as exc:

    print("\n========== TEST FAILED ==========")
    print(type(exc).__name__)
    print(str(exc))