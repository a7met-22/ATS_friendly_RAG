





"""Unified retrieval facade: semantic, keyword, and hybrid search."""

from src.keyword_retrieval import keyword_search

from src.semantic_retrieval import semantic_search


RRF_K = 60


def retrieve_chunks(
    query: str,
    top_k: int = 5,
    document_ids: list[int] | None = None,
    mode: str = "hybrid",
) -> list[dict]:
    """Retrieve chunks using semantic, keyword, or hybrid search.

    Search is restricted to explicitly selected document IDs.
    An empty document selection returns no results.
    """

    if mode not in {
        "semantic",
        "keyword",
        "hybrid",
    }:
        raise ValueError(
            "mode must be 'semantic', 'keyword', or 'hybrid'."
        )

    if (
        not isinstance(query, str)
        or not query.strip()
    ):
        raise ValueError(
            "Query cannot be empty."
        )

    if (
        isinstance(top_k, bool)
        or not isinstance(top_k, int)
        or top_k < 1
    ):
        raise ValueError(
            "top_k must be a positive integer."
        )

    if not document_ids:
        return []

    # Semantic-only retrieval.
    if mode == "semantic":

        return semantic_search(
            query,
            top_k,
            document_ids,
        )

    # Keyword-only retrieval.
    if mode == "keyword":

        return keyword_search(
            query,
            top_k,
            document_ids,
        )

    # Hybrid retrieval.
    candidate_k = max(
        top_k * 3,
        top_k,
    )

    semantic_results = semantic_search(
        query,
        candidate_k,
        document_ids,
    )

    keyword_results = keyword_search(
        query,
        candidate_k,
        document_ids,
    )

    fused: dict[int, dict] = {}

    ranked_lists = (
        semantic_results,
        keyword_results,
    )

    for ranked_results in ranked_lists:

        for rank, result in enumerate(
            ranked_results,
            start=1,
        ):

            chunk_id = result["chunk_id"]

            if chunk_id not in fused:

                fused[chunk_id] = dict(result)

                fused[chunk_id]["retrieval_methods"] = []

                fused[chunk_id]["retrieval_score"] = 0.0

            fused[chunk_id]["retrieval_score"] += (
                1.0 / (RRF_K + rank)
            )

            method = result.get(
                "retrieval_method"
            )

            if (
                method
                and method not in fused[chunk_id]["retrieval_methods"]
            ):
                fused[chunk_id]["retrieval_methods"].append(
                    method
                )

    ranked = sorted(
        fused.values(),
        key=lambda item: item["retrieval_score"],
        reverse=True,
    )

    for result in ranked:
        result["retrieval_method"] = "hybrid"

    return ranked[:top_k]