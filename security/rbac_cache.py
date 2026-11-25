"""Redis cache layer for RBAC role permissions and user profiles (circular-import safe)."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_ROLE_CACHE_PREFIX = "rbac:role_perms:"
_ROLE_CACHE_TTL_SECONDS = 300

_USER_CACHE_PREFIX = "rbac:user_profile:"
_USER_CACHE_TTL_SECONDS = 60


async def _redis():
    from api.security import get_redis_client
    return get_redis_client()


async def get_cached_role_permissions(role_id: int) -> frozenset[str] | None:
    redis = await _redis()
    if redis is None:
        return None
    try:
        raw = await redis.get(f"{_ROLE_CACHE_PREFIX}{role_id}")
        return frozenset(json.loads(raw)) if raw is not None else None
    except Exception as exc:
        logger.warning("RBAC role cache read failed for role %s: %s", role_id, exc)
        return None


async def set_cached_role_permissions(role_id: int, permissions: frozenset[str]) -> None:
    redis = await _redis()
    if redis is None:
        return
    try:
        await redis.setex(
            f"{_ROLE_CACHE_PREFIX}{role_id}",
            _ROLE_CACHE_TTL_SECONDS,
            json.dumps(sorted(permissions)),
        )
    except Exception as exc:
        logger.warning("RBAC role cache write failed for role %s: %s", role_id, exc)


async def invalidate_role_permissions(role_id: int) -> None:
    redis = await _redis()
    if redis is None:
        return
    try:
        await redis.delete(f"{_ROLE_CACHE_PREFIX}{role_id}")
    except Exception as exc:
        logger.warning("RBAC role cache invalidation failed for role %s: %s", role_id, exc)


async def get_cached_user_profile(email: str) -> dict[str, Any] | None:
    redis = await _redis()
    if redis is None:
        return None
    try:
        raw = await redis.get(f"{_USER_CACHE_PREFIX}{email.strip().casefold()}")
        if raw is None:
            return None
        data = json.loads(raw)
        data["permissions"] = frozenset(data.get("permissions", []))
        return data
    except Exception as exc:
        logger.warning("RBAC user cache read failed for %s: %s", email, exc)
        return None


async def set_cached_user_profile(email: str, profile: dict[str, Any]) -> None:
    redis = await _redis()
    if redis is None:
        return
    try:
        serializable = {
            **profile,
            "permissions": sorted(profile.get("permissions", [])),
        }
        await redis.setex(
            f"{_USER_CACHE_PREFIX}{email.strip().casefold()}",
            _USER_CACHE_TTL_SECONDS,
            json.dumps(serializable),
        )
    except Exception as exc:
        logger.warning("RBAC user cache write failed for %s: %s", email, exc)


async def invalidate_user_profile(email: str) -> None:
    redis = await _redis()
    if redis is None:
        return
    try:
        await redis.delete(f"{_USER_CACHE_PREFIX}{email.strip().casefold()}")
    except Exception as exc:
        logger.warning("RBAC user cache invalidation failed for %s: %s", email, exc)
