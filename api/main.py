"""FastAPI Application Entry Point: Lifespan, Middlewares, Security Headers, and Routers."""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.logger import configure_logging, request_id_ctx
from api.routers import admin, auth, chat, documents, health
from api.schemas import ErrorResponse
from api.security import close_redis_client, get_redis_client
from application.services.upload_service import cleanup_expired_session_uploads
from config.settings import (
    CORS_ALLOWED_ORIGINS,
    ENVIRONMENT,
    JWT_SECRET_KEY,
    SESSION_CLEANUP_INTERVAL_HOURS,
    SESSION_MAX_AGE_HOURS,
)
from database_utilities.schema_bootstrap import ensure_database_schema
from database_utilities.database_connection import close_pool, open_pool
from src.llm_provider import close_llm_clients

logger = logging.getLogger(__name__)

_CLEANUP_LOCK_KEY = "lock:periodic_session_cleanup"
_REQ_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{8,64}$")


async def _periodic_session_cleanup_loop() -> None:
    """Background loop that cleans expired guest uploads periodically (leader-elected via Redis)."""
    interval_seconds = SESSION_CLEANUP_INTERVAL_HOURS * 3600
    while True:
        try:
            await asyncio.sleep(interval_seconds)

            redis = get_redis_client()
            if redis is not None:
                acquired = await redis.set(_CLEANUP_LOCK_KEY, "1", nx=True, ex=300)
                if not acquired:
                    continue

            deleted_count = await cleanup_expired_session_uploads(
                max_age_hours=SESSION_MAX_AGE_HOURS
            )
            if deleted_count > 0:
                logger.info(
                    "Periodic cleanup removed %d expired session document(s).",
                    deleted_count,
                )
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Periodic session cleanup iteration failed.")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage startup and graceful shutdown of DB pool, Redis, and background tasks."""
    configure_logging()

    if ENVIRONMENT == "production" and (
        not JWT_SECRET_KEY or "CHANGE_ME" in JWT_SECRET_KEY or len(JWT_SECRET_KEY) < 32
    ):
        raise RuntimeError(
            "FATAL: JWT_SECRET_KEY must be a strong secret (>= 32 chars) in production."
        )

    logger.info("Starting RAG Resume API service (environment=%s)...", ENVIRONMENT)

    # 1. Open PostgreSQL AsyncConnectionPool & verify schema
    await open_pool()

    await ensure_database_schema()


    # 2. Verify Redis connectivity if configured
    redis = get_redis_client()
    if redis is not None:
        try:
            await redis.ping()
            logger.info("Connected to Redis successfully.")
        except Exception as exc:
            logger.warning("Redis unavailable at startup; using In-Memory fallback: %s", exc)

    # 3. Start independent periodic cleanup worker
    cleanup_task = asyncio.create_task(_periodic_session_cleanup_loop())

    yield

    # Graceful Shutdown Sequence
    logger.info("Shutting down RAG Resume API service...")
    cleanup_task.cancel()
    await asyncio.gather(cleanup_task, return_exceptions=True)

    if admin.ACTIVE_SYNC_TASKS:
        for task in list(admin.ACTIVE_SYNC_TASKS):
            task.cancel()
        await asyncio.gather(*admin.ACTIVE_SYNC_TASKS, return_exceptions=True)

    await close_redis_client()
    await close_llm_clients()
    await close_pool()
    logger.info("Shutdown completed cleanly.")


def create_app() -> FastAPI:
    """Application factory configured for production security and observability."""
    is_production = ENVIRONMENT == "production"

    app = FastAPI(
        title="RAG Resume Assistant API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None if is_production else "/docs",
        redoc_url=None if is_production else "/redoc",
        openapi_url=None if is_production else "/openapi.json",
    )

    # 1. Strict CORS Configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Session-ID", "X-Request-ID"],
        expose_headers=["X-Session-ID", "X-Request-ID"],
    )

    # 2. Request Correlation, Session Propagation, and Security Headers Middleware
    @app.middleware("http")
    async def context_and_security_middleware(request: Request, call_next):
        incoming_req_id = (request.headers.get("X-Request-ID") or "").strip()
        req_id = (
            incoming_req_id
            if _REQ_ID_PATTERN.match(incoming_req_id)
            else f"req_{uuid.uuid4().hex[:16]}"
        )
        token = request_id_ctx.set(req_id)
        t0 = time.perf_counter()
        try:
            response = await call_next(request)
            elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
            response.headers["X-Response-Time-Ms"] = str(elapsed_ms)
            response.headers["X-Request-ID"] = req_id
            
            session_id = getattr(request.state, "upload_session_id", None)
            if session_id:
                response.headers["X-Session-ID"] = session_id

            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            return response
        finally:
            request_id_ctx.reset(token)

    # 3. Unified RFC-style Exception Handlers
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        error_map = {
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            409: "CONFLICT",
            413: "PAYLOAD_TOO_LARGE",
            429: "RATE_LIMIT_EXCEEDED",
            503: "SERVICE_UNAVAILABLE",
            504: "GATEWAY_TIMEOUT",
        }
        payload = ErrorResponse(
            error_code=error_map.get(exc.status_code, f"HTTP_{exc.status_code}"),
            message=str(exc.detail),
            request_id=request_id_ctx.get(),
        )
        return JSONResponse(status_code=exc.status_code, content=payload.model_dump())

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        payload = ErrorResponse(
            error_code="VALIDATION_ERROR",
            message="Invalid request parameters or payload format.",
            request_id=request_id_ctx.get(),
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=payload.model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled server exception")
        payload = ErrorResponse(
            error_code="INTERNAL_SERVER_ERROR",
            message="An unexpected internal error occurred.",
            request_id=request_id_ctx.get(),
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=payload.model_dump(),
        )

    # 4. Register Domain Routers
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(documents.router)
    app.include_router(chat.router)
    app.include_router(admin.router)

    return app


app = create_app()
