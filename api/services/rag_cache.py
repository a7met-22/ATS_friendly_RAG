"""Tenant-isolated, content-versioned Redis caching service for Guardrails-verified RAG responses."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from api.security import get_redis_client

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 3600  # 1 hour cache TTL


def build_rag_cache_key(
    *,
    access_level: str,
    document_ids: list[int],
    retrieval_mode: str,
    top_k: int,
    question: str,
    document_versions: list[str] | None = None,
) -> str:
    """Build a deterministic, tenant-isolated, version-aware SHA-256 cache key."""
    doc_signature = sorted(document_versions) if document_versions else sorted(document_ids)
    raw_signature = json.dumps(
        {
            "v": 2,
            "access": access_level,
            "docs": doc_signature,
            "mode": retrieval_mode,
            "top_k": top_k,
            "q": " ".join(question.split()).casefold(),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    digest = hashlib.sha256(raw_signature.encode("utf-8")).hexdigest()
    return f"rag:answer_cache:{digest}"


async def get_cached_rag_answer(cache_key: str) -> dict[str, Any] | None:
    """Retrieve a cached verified answer from Redis (fails open if Redis is unavailable)."""
    redis = get_redis_client()
    if redis is None:
        return None
    try:
        cached_raw = await redis.get(cache_key)
        if cached_raw:
            return json.loads(cached_raw)
    except Exception as exc:
        logger.warning("Redis cache read skipped: %s", exc)
    return None


async def set_cached_rag_answer(cache_key: str, payload: dict[str, Any]) -> None:
    """Store a Guardrails-verified answer in Redis with strict TTL."""
    redis = get_redis_client()
    if redis is None:
        return
    try:
        await redis.setex(
            cache_key,
            _CACHE_TTL_SECONDS,
            json.dumps(payload, ensure_ascii=False),
        )
    except Exception as exc:
        logger.warning("Redis cache write skipped: %s", exc)
