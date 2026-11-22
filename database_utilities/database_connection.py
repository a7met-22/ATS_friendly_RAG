"""High-concurrency PostgreSQL AsyncConnectionPool management."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import psycopg
from psycopg_pool import AsyncConnectionPool

from config.settings import (
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
)

# بناء رابط الاتصال القياسي لـ PostgreSQL
CONNINFO = (
    f"host={DB_HOST} "
    f"port={DB_PORT} "
    f"dbname={DB_NAME} "
    f"user={DB_USER} "
    f"password={DB_PASSWORD} "
    f"connect_timeout=10"
)

_pool: AsyncConnectionPool | None = None


def get_pool() -> AsyncConnectionPool:
    """Create or return the singleton AsyncConnectionPool instance."""
    global _pool

    if _pool is None:
        _pool = AsyncConnectionPool(
            conninfo=CONNINFO,
            min_size=5,          # عدد الاتصالات الجاهزة دائماً في الذاكرة
            max_size=50,         # الحد الأقصى للاتصالات المتزامنة (حسب قدرة سيرفر Postgres)
            max_idle=300,        # إغلاق الاتصالات الزائدة غير المستخدمة بعد 5 دقائق
            timeout=10.0,        # أقصى مدة انتظار للحصول على اتصال متاح من الـ Pool
            open=False,          # الفتح الصريح يتم عبر open_pool() في FastAPI lifespan
            check=AsyncConnectionPool.check_connection,  # فحص سلامة الاتصال قبل تسليمه
        )

    return _pool


async def open_pool() -> None:
    """Initialize and open the connection pool on application startup."""
    pool = get_pool()
    if pool.closed:
        await pool.open(wait=True)


async def close_pool() -> None:
    """Gracefully close all pooled connections on application shutdown."""
    global _pool
    if _pool is not None and not _pool.closed:
        await _pool.close()
        _pool = None



async def get_connection():
    """Borrow an active connection from the pool (compatible with `async with await get_connection()`)."""
    pool = get_pool()

    if pool.closed:
        await pool.open(wait=True)

    return pool.connection()
