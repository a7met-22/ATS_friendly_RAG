"""System health and readiness check router with caching and strict timeouts."""

from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, Response, status

from api.schemas import HealthResponse
from api.security import get_redis_client
from database_utilities.database_connection import get_connection

router = APIRouter(tags=["System"])

_last_check_ts: float = 0.0
_last_healthy: bool = False
_CACHE_TTL_SECONDS: float = 3.0


async def _probe_dependencies() -> bool:
    try:
        async with await get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
                await cur.fetchone()
        redis = get_redis_client()
        if redis is not None:
            await redis.ping()
        return True
    except Exception:
        return False


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Check service readiness",
)
async def health_check(response: Response) -> HealthResponse:
    """Cached 3-second readiness probe to prevent DB/Redis connection flooding."""
    global _last_check_ts, _last_healthy

    now = time.monotonic()
    if now - _last_check_ts >= _CACHE_TTL_SECONDS:
        try:
            _last_healthy = await asyncio.wait_for(_probe_dependencies(), timeout=2.0)
        except asyncio.TimeoutError:
            _last_healthy = False
        _last_check_ts = now

    if not _last_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(status="degraded", database="disconnected")

    return HealthResponse(status="healthy", database="connected")
