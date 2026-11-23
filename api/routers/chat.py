"""Thin HTTP & SSE Streaming controller for RAG Question Answering."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from api.dependencies import (
    enforce_chat_rate_limit,
    get_current_principal,
    get_upload_session_id,
)
from api.schemas import AnswerResponse, ErrorResponse, QuestionRequest
from api.services.chat_orchestrator import (
    GuardrailRejectionError,
    execute_rag_pipeline,
)
from security.authorization import Principal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chat", tags=["RAG Chat"])

_GENERATION_TIMEOUT_SECONDS = 45.0


def _format_sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post(
    "/ask",
    response_model=AnswerResponse,
    dependencies=[Depends(enforce_chat_rate_limit)],
    responses={
        400: {"model": ErrorResponse, "description": "Rejected by input/output Guardrails"},
        403: {"model": ErrorResponse, "description": "Insufficient permissions"},
        429: {"model": ErrorResponse, "description": "Chat rate limit exceeded"},
        504: {"model": ErrorResponse, "description": "Answer generation timed out"},
    },
    summary="Ask a question over accessible CVs (Standard JSON Response)",
)
async def ask_question(
    body: QuestionRequest,
    principal: Principal | None = Depends(get_current_principal),
    upload_session_id: str = Depends(get_upload_session_id),
) -> AnswerResponse:
    """Execute full Guardrails-protected RAG pipeline and return structured JSON."""
    try:
        result = await asyncio.wait_for(
            execute_rag_pipeline(
                body=body,
                principal=principal,
                upload_session_id=upload_session_id,
            ),
            timeout=_GENERATION_TIMEOUT_SECONDS,
        )
    except GuardrailRejectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Request rejected by Guardrails: {exc}",
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Answer generation timed out. Please try again.",
        ) from exc

    return AnswerResponse(**result)


@router.post(
    "/ask/stream",
    dependencies=[Depends(enforce_chat_rate_limit)],
    summary="Ask a question with real-time progress and validated SSE answer streaming",
)
async def ask_question_stream(
    request: Request,
    body: QuestionRequest,
    principal: Principal | None = Depends(get_current_principal),
    upload_session_id: str = Depends(get_upload_session_id),
) -> StreamingResponse:
    """Stream real-time pipeline stages, then stream the Guardrails-verified answer text."""

    async def event_generator() -> AsyncGenerator[str, None]:
        queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=64)

        async def push_progress(step: str, message: str) -> None:
            try:
                queue.put_nowait(_format_sse("status", {"step": step, "message": message}))
            except asyncio.QueueFull:
                pass

        async def run_pipeline() -> dict[str, Any] | None:
            try:
                return await asyncio.wait_for(
                    execute_rag_pipeline(
                        body=body,
                        principal=principal,
                        upload_session_id=upload_session_id,
                        on_progress=push_progress,
                    ),
                    timeout=_GENERATION_TIMEOUT_SECONDS,
                )
            except GuardrailRejectionError as exc:
                await queue.put(
                    _format_sse(
                        "error",
                        {
                            "error_code": "GUARDRAIL_REJECTED",
                            "message": f"Request rejected by Guardrails: {exc}",
                        },
                    )
                )
                return None
            except PermissionError as exc:
                await queue.put(
                    _format_sse(
                        "error",
                        {
                            "error_code": "FORBIDDEN",
                            "message": str(exc),
                        },
                    )
                )
                return None
            except asyncio.TimeoutError:
                await queue.put(
                    _format_sse(
                        "error",
                        {
                            "error_code": "TIMEOUT",
                            "message": "Answer generation timed out.",
                        },
                    )
                )
                return None
            except Exception:
                logger.exception("Unexpected streaming RAG error")
                await queue.put(
                    _format_sse(
                        "error",
                        {
                            "error_code": "INTERNAL_ERROR",
                            "message": "An unexpected error occurred while processing your request.",
                        },
                    )
                )
                return None
            finally:
                await queue.put(None)

        task = asyncio.create_task(run_pipeline())

        try:
            # 1. Stream live progress events as each RAG stage executes
            while True:
                if await request.is_disconnected():
                    task.cancel()
                    return
                event_str = await queue.get()
                if event_str is None:
                    break
                yield event_str

            result = await task
            if result is None:
                return

            # 2. Stream the verified, Guardrails-approved answer text in fast word batches
            words = result["answer"].split(" ")
            batch_size = 4
            for idx in range(0, len(words), batch_size):
                if await request.is_disconnected():
                    return
                piece = " ".join(words[idx : idx + batch_size])
                if idx + batch_size < len(words):
                    piece += " "
                yield _format_sse("chunk", {"text": piece})
                await asyncio.sleep(0.015)

            # 3. Emit verified citations, sources, and metadata, then close stream
            yield _format_sse(
                "metadata",
                {
                    "citations": result.get("citations", []),
                    "sources": result.get("sources", []),
                    "retrieval_mode": result["retrieval_mode"],
                    "documents_searched": result["documents_searched"],
                    "prompt_access_level": result["prompt_access_level"],
                },
            )
            yield _format_sse("done", {"status": "completed"})
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
