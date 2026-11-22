"""Async RAG question answering with access-level-specific prompt policies."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

from application.services.document_scope import (
    resolve_search_document_ids,
)
from guardrails import inspect_message
from prompts.registry import get_system_prompt
from security.authorization import (
    PERMISSION_SYSTEM_SEARCH,
    Principal,
    require_permission,
)
from src.answer_generation import generate_answer
from src.retrieval import retrieve_chunks


async def _inspect_user_question_async(question: str) -> dict[str, Any]:
    """Run input guardrails off the main Event Loop."""
    if inspect.iscoroutinefunction(inspect_message):
        return await inspect_message(content=question, message_type="user")
    return await asyncio.to_thread(
        inspect_message,
        content=question,
        message_type="user",
    )


async def answer_question(
    *,
    question: str,
    upload_session_id: str,
    principal: Principal | None,
    include_session_uploads: bool = False,
    top_k: int = 5,
    retrieval_mode: str = "hybrid",
    debug: bool = False,
) -> dict[str, Any]:
    """Manage access, retrieval, prompt selection, and answer generation asynchronously."""

    # 1. Validate the user's question.
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Question cannot be empty.")

    question = question.strip()

    # 2. Determine access level and validate permissions early (fast in-memory check).
    system_access = principal is not None

    if system_access:
        require_permission(
            principal,
            PERMISSION_SYSTEM_SEARCH,
        )
    else:
        # Guests cannot expand their search scope.
        include_session_uploads = False

    # 3. Question inspection and validation via Guardrails.
    inspection = await _inspect_user_question_async(question)

    if not inspection["ok"]:
        raise ValueError(
            f"Question rejected by Guardrails: {inspection['error']}"
        )

    validated_question = inspection["extracted_text"]

    # 4. Resolve the documents available to this user.
    document_ids = await resolve_search_document_ids(
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

    # 5. Stop if no documents are available.
    if not document_ids:
        return {
            "answer": (
                "No processed documents are available "
                "in your current search scope."
            ),
            "sources": [],
            "citations": [],
            **response_metadata,
        }

    # 6. Retrieve relevant chunks (Hybrid: Parallel Semantic + Keyword).
    chunks = await retrieve_chunks(
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
            "citations": [],
            **response_metadata,
        }

    # 7. Select the appropriate system prompt.
    system_instruction = get_system_prompt(
        authenticated_system_access=system_access
    )

    # 8. Generate the final answer using the retrieved chunks.
    generated = await generate_answer(
        question=validated_question,
        chunks=chunks,
        system_instruction=system_instruction,
        debug=debug,
    )

    # 9. Return the answer and application-level metadata.
    return {
        **generated,
        **response_metadata,
    }
