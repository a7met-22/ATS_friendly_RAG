"""Async Google Gemini embedding utilities."""

import asyncio
import logging
import math
import random
import re
from typing import Any

from google import genai
from google.genai import types
from google.genai.errors import APIError

from config.settings import GEMINI_API_KEY, EMBEDDING_MODEL


logger = logging.getLogger(__name__)

EMBED_MODEL_NAME = EMBEDDING_MODEL
EMBEDDING_DIMENSIONS = 768
EMBEDDING_BATCH_SIZE = 5
MAX_CONCURRENT_BATCHES = 3  # صمام الأمان: بحد أقصى 3 طلبات متزامنة لـ Gemini

EMBEDDING_RPM_LIMIT = 50

MAX_RETRY_ATTEMPTS = 3
MAX_AUTOMATIC_WAIT_SECONDS = 60
INITIAL_RETRY_DELAY = 2
MAX_RETRY_DELAY = 60

RETRYABLE_STATUS_CODES = {
    408, 429, 500, 502, 503, 504
}

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """Create the Gemini client lazily (Sync - fast in-memory init)."""
    global _client

    if _client is None:
        if not GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY is missing from configuration."
            )

        _client = genai.Client(
            api_key=GEMINI_API_KEY,
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(
                    attempts=1
                )
            ),
        )

    return _client


def normalize_embedding(
    values: list[float],
) -> list[float]:
    """Return an L2-normalized embedding vector (Sync - pure math)."""
    vector = [float(value) for value in values]

    if len(vector) != EMBEDDING_DIMENSIONS:
        raise ValueError(
            f"Expected {EMBEDDING_DIMENSIONS} dimensions, "
            f"received {len(vector)}."
        )

    if not all(math.isfinite(value) for value in vector):
        raise ValueError(
            "Embedding contains a non-finite value."
        )

    norm = math.sqrt(sum(value * value for value in vector))

    if norm == 0:
        raise ValueError(
            "Embedding norm is zero and cannot be normalized."
        )

    return [value / norm for value in vector]


def _extract_retry_delay(
    data: Any,
) -> float | None:
    """Extract retryDelay from Google's nested error response (Sync)."""
    if isinstance(data, dict):
        retry_delay = data.get("retryDelay")

        if isinstance(retry_delay, str):
            match = re.fullmatch(
                r"\s*(\d+(?:\.\d+)?)s\s*",
                retry_delay,
            )
            if match:
                return float(match.group(1))

        for value in data.values():
            result = _extract_retry_delay(value)
            if result is not None:
                return result

    elif isinstance(data, list):
        for item in data:
            result = _extract_retry_delay(item)
            if result is not None:
                return result

    return None


async def _embed_batch_with_retry(
    client: genai.Client,
    batch: list[str],
    task_type: str,
):
    """Call Gemini asynchronously with bounded retry and non-blocking backoff."""
    for attempt in range(MAX_RETRY_ATTEMPTS):
        try:
            # استخدام الواجهة غير المتزامنة client.aio
            return await client.aio.models.embed_content(
                model=EMBED_MODEL_NAME,
                contents=batch,
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=EMBEDDING_DIMENSIONS,
                ),
            )

        except APIError as exc:
            if (
                exc.code not in RETRYABLE_STATUS_CODES
                or attempt == MAX_RETRY_ATTEMPTS - 1
            ):
                raise

            server_delay = _extract_retry_delay(
                getattr(exc, "details", None)
            )

            # Never block the application for a long quota reset.
            if (
                server_delay is not None
                and server_delay > MAX_AUTOMATIC_WAIT_SECONDS
            ):
                raise RuntimeError(
                    "Gemini requested a retry after "
                    f"{server_delay:,.0f} seconds "
                    f"(approximately {server_delay / 3600:.1f} hours). "
                    "Automatic retry was cancelled to avoid a long wait. "
                    "Check your Gemini API quota and try again later."
                ) from exc

            if server_delay is None:
                delay = min(
                    INITIAL_RETRY_DELAY * (2 ** attempt),
                    MAX_AUTOMATIC_WAIT_SECONDS,
                )
            else:
                delay = server_delay

            delay = min(
                delay + random.uniform(0, 1),
                MAX_AUTOMATIC_WAIT_SECONDS,
            )

            logger.warning(
                "Gemini API error %s. "
                "Retrying in %.1f seconds. Attempt %s/%s.",
                exc.code,
                delay,
                attempt + 1,
                MAX_RETRY_ATTEMPTS,
            )

            # انتظار غير معطل (Non-blocking sleep)
            await asyncio.sleep(delay)

    raise RuntimeError(
        "Gemini embedding retry attempts exhausted."
    )


async def generate_embeddings(
    texts: list[str],
    task_type: str = "RETRIEVAL_DOCUMENT",
) -> list[list[float]]:
    """Generate normalized embeddings concurrently in batches."""
    if not texts:
        return []

    if any(
        not isinstance(text, str) or not text.strip()
        for text in texts
    ):
        raise ValueError(
            "Embedding texts must be non-empty strings."
        )

    valid_task_types = {
        "RETRIEVAL_DOCUMENT",
        "RETRIEVAL_QUERY",
        "SEMANTIC_SIMILARITY",
        "CLASSIFICATION",
        "CLUSTERING",
    }

    if task_type not in valid_task_types:
        raise ValueError(
            f"Unsupported embedding task type: {task_type}"
        )

    client = _get_client()

    # تقسيم النصوص إلى مجموعات (Batches)
    batches = [
        texts[start : start + EMBEDDING_BATCH_SIZE]
        for start in range(0, len(texts), EMBEDDING_BATCH_SIZE)
    ]

    # صمام الأمان: يسمح بـ 3 Batches بالتوازي كحد أقصى لتفادي Rate Limit
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_BATCHES)
    min_interval = (EMBEDDING_BATCH_SIZE * 60.0) / EMBEDDING_RPM_LIMIT

    async def _process_single_batch(batch: list[str]) -> list[list[float]]:
        async with semaphore:
            response = await _embed_batch_with_retry(
                client=client,
                batch=batch,
                task_type=task_type,
            )

            # تهدئة بسيطة غير معطلة لاحترام حد الـ RPM
            await asyncio.sleep(min_interval / MAX_CONCURRENT_BATCHES)

            returned = getattr(response, "embeddings", None)
            if not returned or len(returned) != len(batch):
                raise RuntimeError(
                    "Embedding response count does not match input count."
                )

            batch_vectors = []
            for item in returned:
                values: Any = getattr(item, "values", None)
                if values is None:
                    raise RuntimeError(
                        "Gemini returned an embedding without values."
                    )
                batch_vectors.append(normalize_embedding(values))

            return batch_vectors

    # تشغيل كل الـ Batches بالتوازي مع الحفاظ على الترتيب الدقيق
    tasks = [_process_single_batch(batch) for batch in batches]
    batch_results = await asyncio.gather(*tasks)

    # تجميع القوائم الفرعية في قائمة واحدة بنفس ترتيب النصوص الأصلية
    embeddings: list[list[float]] = [
        vector
        for batch_list in batch_results
        for vector in batch_list
    ]

    return embeddings
