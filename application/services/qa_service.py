


"""RAG question answering with access-level-specific prompt policies."""

from __future__ import annotations

from guardrails import inspect_message

from prompts.registry import get_system_prompt

from security.authorization import (
    PERMISSION_SYSTEM_SEARCH,
    Principal,
    require_permission,
)

from application.services.document_scope import (
    resolve_search_document_ids,
)

from src.retrieval import retrieve_chunks
from src.answer_generation import generate_answer


def answer_question(
    *,
    question: str,
    upload_session_id: str,
    principal: Principal | None,
    include_session_uploads: bool = False,
    top_k: int = 5,
    retrieval_mode: str = "hybrid",
) -> dict:
    """Manage access, retrieval, prompt selection, and answer generation."""

    # 1. Validate the user's question.
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Question cannot be empty.")

    question = question.strip()

    #Question inspection and validation.
    result = inspect_message(
        content=question,
        message_type="user",
    )

    if not result["ok"]:

        print(result["error"])
        return {
                    **result,
                    **response_metadata,
                }

    else:

        validated_question = result["extracted_text"]

        question_json = result["json_text"]

        # 2. Determine access level and validate permissions.
        system_access = principal is not None

        if system_access:
            require_permission(
                principal,
                PERMISSION_SYSTEM_SEARCH,
            )

        else:
            # Guests cannot expand their search scope.
            include_session_uploads = False

        # 3. Resolve the documents available to this user.
        document_ids = resolve_search_document_ids(
            principal=principal,
            upload_session_id=upload_session_id,
            include_session_uploads=include_session_uploads,
        )

        # Common response metadata.
        response_metadata = {
            "retrieval_mode": retrieval_mode,
            "documents_searched": len(document_ids),
            "prompt_access_level": (
                "system" if system_access else "guest"
            ),
        }

        # 4. Stop if no documents are available.
        if not document_ids:
            return {
                "answer": (
                    "No processed documents are available "
                    "in your current search scope."
                ),
                "sources": [],
                **response_metadata,
            }

        # 5. Retrieve relevant chunks.
        chunks = retrieve_chunks(
            query=validated_question,
            top_k=top_k,
            document_ids=document_ids,
            mode=retrieval_mode,
        )

        if not chunks:
            return {
                "answer": (
                    "I could not find relevant information "
                    "in the selected documents."
                ),
                "sources": [],
                **response_metadata,
            }

        # 6. Select the appropriate system prompt.
        system_instruction = get_system_prompt(
            authenticated_system_access=system_access
        )

        # 7. Generate the final answer using the retrieved chunks.
        result = generate_answer(
            question=validated_question,
            chunks=chunks,
            system_instruction=system_instruction,
        )

        # 8. Return the answer and application-level metadata.
        return {
            **result,
            **response_metadata,
        }