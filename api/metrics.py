"""Unified RAG Telemetry: LangSmith Trace Spans + Structured Latency & Cache Metrics."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from api.logger import request_id_ctx

logger = logging.getLogger(__name__)

# التحقق الآمن من وجود مكتبة langsmith وتفعيل التتبع في البيئة
try:
    from langsmith import traceable
    from langsmith.run_helpers import get_current_run_tree

    _LANGSMITH_AVAILABLE = True
except ImportError:
    _LANGSMITH_AVAILABLE = False


def is_langsmith_enabled() -> bool:
    """Return True only when langsmith is installed and LANGSMITH_TRACING=true."""
    if not _LANGSMITH_AVAILABLE:
        return False
    return os.getenv("LANGSMITH_TRACING", "false").strip().lower() == "true"


@dataclass
class RagPipelineMetrics:
    """Collects per-stage latency (ms), cache status, and token/cost metadata for a RAG request."""

    access_level: str
    retrieval_mode: str
    documents_searched: int = 0
    chunks_retrieved: int = 0
    cache_hit: bool = False
    timings_ms: dict[str, float] = field(default_factory=dict)
    _start_time: float = field(default_factory=time.perf_counter)

    @asynccontextmanager
    async def measure_stage(self, stage_name: str) -> AsyncGenerator[None, None]:
        """Async context manager that times a pipeline stage and attaches metadata to LangSmith."""
        t0 = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
            self.timings_ms[stage_name] = elapsed_ms

            if is_langsmith_enabled():
                try:
                    run_tree = get_current_run_tree()
                    if run_tree is not None:
                        run_tree.add_metadata({
                            f"{stage_name}_ms": elapsed_ms,
                            "request_id": request_id_ctx.get(),
                        })
                except Exception:
                    pass

    def emit_summary(self, status: str = "success") -> None:
        """Emit a single structured JSON metric log entry and enrich active LangSmith trace."""
        total_ms = round((time.perf_counter() - self._start_time) * 1000, 2)
        summary = {
            "event": "RAG_PIPELINE_METRICS",
            "status": status,
            "access_level": self.access_level,
            "retrieval_mode": self.retrieval_mode,
            "documents_searched": self.documents_searched,
            "chunks_retrieved": self.chunks_retrieved,
            "cache_hit": self.cache_hit,
            "total_ms": total_ms,
            "stages_ms": self.timings_ms,
        }

        if is_langsmith_enabled():
            try:
                run_tree = get_current_run_tree()
                if run_tree is not None:
                    run_tree.add_metadata(summary)
                    run_tree.add_tags([
                        f"access:{self.access_level}",
                        f"mode:{self.retrieval_mode}",
                        "cache:hit" if self.cache_hit else "cache:miss",
                    ])
            except Exception:
                pass

        logger.info("RAG metrics summary: %s", summary)


def trace_rag_pipeline(func):
    """Decorator that wraps execute_rag_pipeline in a root LangSmith chain run when enabled."""
    if not _LANGSMITH_AVAILABLE:
        return func
    return traceable(name="rag_chat_pipeline", run_type="chain")(func)
