"""Stateless JWT token management and distributed Redis / In-Memory rate limiting."""

from __future__ import annotations

import logging
import os
import time
import uuid
from abc import ABC, abstractmethod
from collections import deque
from datetime import datetime, timezone

import jwt
from fastapi import HTTPException, status
from redis.asyncio import Redis

from config.settings import JWT_ALGORITHM, JWT_SECRET_KEY
from security.authorization import Principal

logger = logging.getLogger(__name__)

_redis_client: Redis | None = None


def get_redis_client() -> Redis | None:
    """Return an active async Redis client if REDIS_URL is configured."""
    global _redis_client
    redis_url = os.getenv("REDIS_URL", "").strip()
    if not redis_url:
        return None
    if _redis_client is None:
        _redis_client = Redis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
        )
    return _redis_client


async def close_redis_client() -> None:
    """Gracefully close the Redis connection pool on shutdown."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


def create_access_token(principal: Principal) -> tuple[str, int]:
    """Encode an authenticated Principal into a signed JWT token."""
    now = datetime.now(timezone.utc)
    expires_in = max(int((principal.expires_at - now).total_seconds()), 60)

    payload = {
        "sub": principal.email,
        "roles": list(principal.roles),
        "iat": int(principal.authenticated_at.timestamp()),
        "exp": int(principal.expires_at.timestamp()),
    }

    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return token, expires_in


def decode_access_token(token: str) -> Principal:
    """Decode and validate a JWT token back into a Principal object."""
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "roles", "iat", "exp"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired.",
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
        ) from exc

    return Principal(
        email=str(payload["sub"]),
        roles=frozenset(payload["roles"]),
        authenticated_at=datetime.fromtimestamp(payload["iat"], tz=timezone.utc),
        expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
    )


class BaseRateLimiter(ABC):
    """Unified interface for distributed or local rate limiters."""

    def __init__(self, bucket: str, max_requests: int, window_seconds: int = 60) -> None:
        self.bucket = bucket
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    @abstractmethod
    async def check(self, client_key: str) -> None:
        """Raise HTTP 429 if the client exceeded the allowed request rate."""

    @abstractmethod
    async def reset(self, client_key: str) -> None:
        """Clear recorded attempts for a client key (e.g. after successful login)."""


class InMemoryRateLimiter(BaseRateLimiter):
    """Memory-safe sliding-window rate limiter for single-worker fallback."""

    def __init__(self, bucket: str, max_requests: int, window_seconds: int = 60) -> None:
        super().__init__(bucket, max_requests, window_seconds)
        self._hits: dict[str, deque[float]] = {}

    async def check(self, client_key: str) -> None:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        timestamps = self._hits.get(client_key)

        if timestamps is not None:
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()

            if len(timestamps) >= self.max_requests:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded. Please wait before sending more requests.",
                )

            timestamps.append(now)
        else:
            self._hits[client_key] = deque([now])

        if len(self._hits) > 10_000:
            expired_keys = [
                k for k, dq in self._hits.items()
                if not dq or dq[-1] <= cutoff
            ]
            for k in expired_keys:
                del self._hits[k]

    async def reset(self, client_key: str) -> None:
        self._hits.pop(client_key, None)


_REDIS_SLIDING_WINDOW_LUA = """

local key = KEYS[1]             -- اسم العداد الخاص بالمستخدم (مثل: ratelimit:guest_chat:192.168.1.5)
local now = tonumber(ARGV[1])   -- التوقيت الحالي بالمللي ثانية
local window = tonumber(ARGV[2])-- مدة النافذة الزمنية (60,000 مللي ثانية = دقيقة)
local limit = tonumber(ARGV[3]) -- الحد الأقصى المسموح (مثلاً 20 طلب)
local member = ARGV[4]          -- بصمة فريدة لهذا الطلب

redis.call('ZREMRANGEBYSCORE', key, 0, now - window) -- 1. امسح أي طلبات قديمة مر عليها أكثر من دقيقة
local current = redis.call('ZCARD', key)             -- 2. احسب عدد الطلبات المتبقية في آخر دقيقة
if current >= limit then                             -- 3. لو وصل للحد الأقصى (20) ارفض الطلب فوراً
    return 0
end
redis.call('ZADD', key, now, member)                 -- 4. سجّل هذا الطلب الجديد بالوقت الحالي
redis.call('PEXPIRE', key, window)                   -- 5. اضبط عداد المسح التلقائي للذاكرة بعد دقيقة
return 1   
"""


class DistributedRateLimiter(BaseRateLimiter):
    """Uses Redis atomic sliding window when available, falling back safely to In-Memory."""

    def __init__(self, bucket: str, max_requests: int, window_seconds: int = 60) -> None:
        super().__init__(bucket, max_requests, window_seconds)
        self._fallback = InMemoryRateLimiter(bucket, max_requests, window_seconds)

    async def check(self, client_key: str) -> None:
        redis = get_redis_client()
        if redis is None:
            await self._fallback.check(client_key)
            return

        redis_key = f"ratelimit:{self.bucket}:{client_key}"
        now_ms = int(time.time() * 1000)
        window_ms = self.window_seconds * 1000
        member = f"{now_ms}:{uuid.uuid4().hex[:8]}"

        try:
            allowed = await redis.eval(
                _REDIS_SLIDING_WINDOW_LUA,
                1,
                redis_key,
                now_ms,
                window_ms,
                self.max_requests,
                member,
            )
        except Exception as exc:
            logger.warning("Redis rate limiter fallback triggered: %s", exc)
            await self._fallback.check(client_key)
            return

        if int(allowed) == 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please wait before sending more requests.",
            )

    async def reset(self, client_key: str) -> None:
        await self._fallback.reset(client_key)
        redis = get_redis_client()
        if redis is not None:
            try:
                await redis.delete(f"ratelimit:{self.bucket}:{client_key}")
            except Exception:
                pass


login_rate_limiter = DistributedRateLimiter("login", max_requests=10, window_seconds=60)
guest_chat_limiter = DistributedRateLimiter("guest_chat", max_requests=20, window_seconds=60)
user_chat_limiter = DistributedRateLimiter("user_chat", max_requests=60, window_seconds=60)
upload_rate_limiter = DistributedRateLimiter("upload", max_requests=10, window_seconds=60)

