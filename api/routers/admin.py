


"""Administrative & authorized operations router (Google Drive sync with atomic Redis locking)."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import require_drive_sync_user
from api.schemas import ErrorResponse, SyncTriggerResponse
from api.security import get_redis_client
from orchestrator.orchestration import sync_drive_documents
from security.authorization import Principal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["Administration"])

_SYNC_LOCK_KEY = "lock:google_drive_sync"
_SYNC_STATUS_KEY = "status:google_drive_sync"
_SYNC_LOCK_TTL_SECONDS = 1800  # 30 minutes safety TTL
_local_sync_lock = asyncio.Lock()

# الاحتفاظ بمراجع المهام الخلفية لمنع الـ Garbage Collector من حذفها أثناء التشغيل
ACTIVE_SYNC_TASKS: set[asyncio.Task[None]] = set()

# Lua script ذري يفك القفل فقط إذا كان مملوكاً لنفس المهمة (يمنع مسح قفل سيرفر آخر)
_RELEASE_LOCK_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


async def _acquire_sync_lock(owner_token: str) -> bool:
    """Acquire an atomic distributed lock owned strictly by owner_token."""
    redis = get_redis_client()
    if redis is not None:
        try:
            acquired = await redis.set(
                _SYNC_LOCK_KEY,
                owner_token,
                nx=True,
                ex=_SYNC_LOCK_TTL_SECONDS,
            )
            return bool(acquired)
        except Exception as exc:
            logger.warning("Redis sync lock fallback triggered: %s", exc)

    if _local_sync_lock.locked():
        return False
    await _local_sync_lock.acquire()
    return True


async def _release_sync_lock(owner_token: str) -> None:
    """Release the distributed lock only if still owned by owner_token."""
    redis = get_redis_client()
    if redis is not None:
        try:
            await redis.eval(_RELEASE_LOCK_LUA, 1, _SYNC_LOCK_KEY, owner_token)
        except Exception as exc:
            logger.warning("Failed to release Redis sync lock: %s", exc)

    if _local_sync_lock.locked():
        _local_sync_lock.release()


async def _update_sync_status(state: dict[str, Any]) -> None:
    """Persist latest Drive sync status in Redis for operational visibility."""
    redis = get_redis_client()
    if redis is None:
        return
    try:
        await redis.setex(_SYNC_STATUS_KEY, 86400, json.dumps(state, ensure_ascii=False))
    except Exception as exc:
        logger.warning("Failed to update sync status in Redis: %s", exc)


async def _run_drive_sync_job(triggered_by: str, owner_token: str) -> None:
    """Background worker dedicated exclusively to Google Drive synchronization."""
    started_at = datetime.now(timezone.utc).isoformat()
    logger.info("Starting background Google Drive sync triggered by %s", triggered_by)

    await _update_sync_status({
        "status": "running",
        "triggered_by": triggered_by,
        "started_at": started_at,
    })

    try:
        summary = await sync_drive_documents()
        finished_at = datetime.now(timezone.utc).isoformat()
        logger.info("Background Google Drive sync completed: %s", summary)
        await _update_sync_status({
            "status": "completed",
            "triggered_by": triggered_by,
            "started_at": started_at,
            "finished_at": finished_at,
            "summary": summary,
        })
    except asyncio.CancelledError:
        logger.warning("Background Google Drive sync was cancelled due to server shutdown.")
        await _update_sync_status({
            "status": "cancelled",
            "triggered_by": triggered_by,
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        })
        raise
    except Exception as exc:
        logger.exception("Background Google Drive sync failed")
        await _update_sync_status({
            "status": "failed",
            "triggered_by": triggered_by,
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "error": type(exc).__name__,
        })
    finally:
        await _release_sync_lock(owner_token)


@router.post(
    "/sync-drive",
    response_model=SyncTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {"model": ErrorResponse, "description": "Insufficient permissions"},
        409: {"model": ErrorResponse, "description": "A Drive sync job is already running"},
    },
    summary="Trigger asynchronous Google Drive CV synchronization",
)
async def trigger_drive_sync(
    principal: Principal = Depends(require_drive_sync_user),
) -> SyncTriggerResponse:
    """Start Google Drive sync in the background for authorized 'admin' or 'system_search' users."""
    owner_token = uuid.uuid4().hex
    acquired = await _acquire_sync_lock(owner_token)
    if not acquired:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A Google Drive synchronization job is already in progress.",
        )

    task = asyncio.create_task(
        _run_drive_sync_job(triggered_by=principal.email, owner_token=owner_token)
    )
    ACTIVE_SYNC_TASKS.add(task)
    task.add_done_callback(ACTIVE_SYNC_TASKS.discard)

    return SyncTriggerResponse(
        status="accepted",
        message="Google Drive synchronization started in the background.",
    )


@router.get(
    "/sync-status",
    summary="Get the status of the current or latest Google Drive synchronization",
)
async def get_drive_sync_status(
    principal: Principal = Depends(require_drive_sync_user),
) -> dict[str, Any]:
    """Retrieve latest Drive sync execution status from Redis."""
    redis = get_redis_client()
    if redis is not None:
        try:
            raw = await redis.get(_SYNC_STATUS_KEY)
            if raw:
                return json.loads(raw)
        except Exception:
            pass
    return {"status": "idle"}
