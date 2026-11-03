"""Test Google embedding generation."""

from src.embeddings import generate_embedding, EMBEDDING_DIMENSIONS

text = "Python developer with experience in machine learning."

vector = generate_embedding(text)

print("PASS: Embedding generated successfully.")
print(f"Vector dimensions: {len(vector)}")
print(f"First 5 values: {vector[:5]}")

assert len(vector) == EMBEDDING_DIMENSIONS
assert all(isinstance(value, float) for value in vector)

print("PASS: Embedding validation completed.")