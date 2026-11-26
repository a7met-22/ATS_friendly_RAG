


"""Core RAG execution pipeline with RBAC, Input/Output Guardrails, and progress hooks."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from api.schemas import QuestionRequest
from api.services.rag_cache import (
    build_rag_cache_key,
    get_cached_rag_answer,
    set_cached_rag_answer,
)
from application.services.document_scope import (
    get_document_version_fingerprints,
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
from api.metrics import RagPipelineMetrics, trace_rag_pipeline



class GuardrailRejectionError(ValueError):
    """Raised when user input or model output fails Guardrails inspection."""


async def _inspect_user_input(question: str) -> str:
    """Run input guardrails off the main event loop."""
    if inspect.iscoroutinefunction(inspect_message):
        res = await inspect_message(content=question, message_type="user")
    else:
        res = await asyncio.to_thread(
            inspect_message,
            content=question,
            message_type="user",
        )

    if not res.get("ok"):
        raise GuardrailRejectionError(
            res.get("error") or "Question rejected by security policy."
        )
    return res["extracted_text"]


@trace_rag_pipeline
async def execute_rag_pipeline(
    *,
    body: QuestionRequest,
    principal: Principal | None,
    upload_session_id: str,
    on_progress: Callable[[str, str], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    """Execute end-to-end Guardrails-protected RAG workflow with LangSmith tracing and stage metrics."""
    system_access = principal is not None
    access_level = "system" if system_access else "guest"
    metrics = RagPipelineMetrics(access_level=access_level, retrieval_mode=body.retrieval_mode)

    try:
        if system_access:
            require_permission(principal, PERMISSION_SYSTEM_SEARCH)
            include_session_uploads = body.include_session_uploads
        else:
            include_session_uploads = True

        if on_progress:
            await on_progress("validating_input", "Validating question against security policies...")

        async with metrics.measure_stage("input_guardrails"):
            validated_question = await _inspect_user_input(body.question.strip())

        if on_progress:
            await on_progress("resolving_scope", "Resolving accessible documents...")

        async with metrics.measure_stage("scope_and_cache"):
            document_ids = await resolve_search_document_ids(
                principal=principal,
                upload_session_id=upload_session_id,
                include_session_uploads=include_session_uploads,
            )
            metrics.documents_searched = len(document_ids)

            response_metadata = {
                "retrieval_mode": body.retrieval_mode,
                "documents_searched": len(document_ids),
                "prompt_access_level": access_level,
            }

            if not document_ids:
                metrics.emit_summary(status="empty_scope")
                return {
                    "answer": "No processed documents are available in your current search scope.",
                    "sources": [],
                    "citations": [],
                    **response_metadata,
                }

            document_versions = await get_document_version_fingerprints(document_ids)
            cache_key = build_rag_cache_key(
                access_level=access_level,
                document_ids=document_ids,
                document_versions=document_versions,
                retrieval_mode=body.retrieval_mode,
                top_k=body.top_k,
                question=validated_question,
            )
            cached = await get_cached_rag_answer(cache_key)
            if cached is not None:
                metrics.cache_hit = True
                if on_progress:
                    await on_progress("cache_hit", "Retrieved verified answer from cache.")
                metrics.emit_summary(status="cache_hit")
                return cached

        if on_progress:
            await on_progress(
                "retrieving_chunks",
                f"Searching across {len(document_ids)} document(s) using {body.retrieval_mode} mode...",
            )

        async with metrics.measure_stage("hybrid_retrieval"):
            chunks = await retrieve_chunks(
                query=validated_question,
                top_k=body.top_k,
                document_ids=document_ids,
                mode=body.retrieval_mode,
            )
            metrics.chunks_retrieved = len(chunks)

        if not chunks:
            metrics.emit_summary(status="no_chunks")
            return {
                "answer": "I could not find relevant information in the selected documents.",
                "sources": [],
                "citations": [],
                **response_metadata,
            }

        if on_progress:
            await on_progress("generating_answer", "Generating and verifying structured answer...")

        system_instruction = get_system_prompt(authenticated_system_access=system_access)

        async with metrics.measure_stage("llm_and_output_guardrails"):
            try:
                generated = await generate_answer(
                    question=validated_question,
                    chunks=chunks,
                    system_instruction=system_instruction,
                )
            except ValueError as exc:
                raise GuardrailRejectionError(str(exc)) from exc

        final_payload = {
            **generated,
            **response_metadata,
        }

        await set_cached_rag_answer(cache_key, final_payload)
        metrics.emit_summary(status="success")
        return final_payload
    except GuardrailRejectionError:
        metrics.emit_summary(status="guardrail_rejected")
        raise
    except Exception:
        metrics.emit_summary(status="error")
        raise
