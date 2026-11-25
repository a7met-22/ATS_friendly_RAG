"""FastAPI Dependency Injection: Authentication, Guest Sessions, RBAC, Rate Limits, and Parsers."""

from __future__ import annotations

import os
import re
import uuid
from functools import lru_cache
from typing import Any

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.security import (
    decode_access_token,
    guest_chat_limiter,
    login_rate_limiter,
    user_chat_limiter,
)
from config.settings import PARSER_TYPE
from parsingWays.llama_parsing import create_drive_parser
from parsingWays.pymupdf_parsing import parse_pdf_bytes as pymupdf_parser
from security.authorization import (
    PERMISSION_SYSTEM_SEARCH,
    Principal,
    _load_bootstrap_users,
    has_permission,
    is_principal_active,
)
from security.roles_repository import fetch_role_permissions

from security.authorization import (
    Principal,
    _load_bootstrap_users,
    has_permission,
    is_principal_active,
)
from security.users_repository import get_user_by_email



_bearer_scheme = HTTPBearer(auto_error=False)
_SESSION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{16,64}$")


def get_client_ip(request: Request) -> str:
    """Extract client IP safely, trusting X-Forwarded-For only when behind a configured proxy."""
    trust_proxy = os.getenv("TRUST_PROXY_HEADERS", "false").strip().lower() == "true"
    if trust_proxy:
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

    if request.client and request.client.host:
        return request.client.host
    return "unknown"


async def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> Principal | None:
    """Resolve authenticated Principal from Bearer JWT and verify live account & permissions (DB + .env)."""
    if credentials is None or not credentials.credentials:
        return None

    principal = decode_access_token(credentials.credentials)

    if not is_principal_active(principal):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated session has expired. Please sign in again.",
        )

    normalized_email = principal.email.strip().casefold()

    # 1. التحقق أولاً من قاعدة البيانات (المستخدمون المضافون من لوحة الأدمن)
    db_user = await get_user_by_email(normalized_email)
    if db_user is not None:
        if not db_user["is_active"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="This user account has been deactivated.",
            )
        return Principal(
            email=db_user["email"],
            roles=frozenset({db_user["role_name"]}),
            authenticated_at=principal.authenticated_at,
            expires_at=principal.expires_at,
            permissions=db_user["permissions"],
            full_name=db_user["full_name"],
            user_id=db_user["id"],
        )

    # 2. التحقق من حسابات الطوارئ في .env (Bootstrap Admin)
    bootstrap_user = _load_bootstrap_users().get(normalized_email)
    if bootstrap_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is no longer authorized.",
        )

    return Principal(
        email=principal.email,
        roles=bootstrap_user["roles"],
        authenticated_at=principal.authenticated_at,
        expires_at=principal.expires_at,
        permissions=bootstrap_user["permissions"],
    )


def require_permission_dep(permission_code: str):
    """Reusable FastAPI dependency factory enforcing any RBAC permission code."""
    async def _checker(
        principal: Principal | None = Depends(get_current_principal),
    ) -> Principal:
        if principal is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required.",
            )
        if not has_permission(principal, permission_code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission_code}",
            )
        return principal

    return _checker



async def require_authenticated_user(
    principal: Principal | None = Depends(get_current_principal),
) -> Principal:
    """Ensure the request belongs to an active authenticated user."""
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to access this resource.",
        )
    return principal


async def require_system_search_user(
    principal: Principal = Depends(require_authenticated_user),
) -> Principal:
    """Ensure the authenticated user has system document search permissions."""
    if not has_permission(principal, PERMISSION_SYSTEM_SEARCH):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to search system documents.",
        )
    return principal


async def require_drive_sync_user(
    principal: Principal = Depends(require_authenticated_user),
) -> Principal:
    """Allow both 'admin' and 'system_search' roles to trigger Google Drive sync."""
    if not has_permission(principal, PERMISSION_SYSTEM_SEARCH):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System search or administrator privileges are required for this operation.",
        )
    return principal


async def get_upload_session_id(
    request: Request,
    x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
) -> str:
    """Extract and validate X-Session-ID header, or generate a new isolated session ID."""
    if x_session_id is not None and x_session_id.strip():
        cleaned = x_session_id.strip()
        if not _SESSION_ID_PATTERN.match(cleaned):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid X-Session-ID format. Must be 16-64 alphanumeric characters.",
            )
        session_id = cleaned
    else:
        session_id = uuid.uuid4().hex

    request.state.upload_session_id = session_id
    return session_id


async def enforce_login_rate_limit(request: Request) -> None:
    """Protect the login endpoint from brute-force attacks."""
    client_ip = get_client_ip(request)
    await login_rate_limiter.check(client_ip)


async def enforce_chat_rate_limit(
    request: Request,
    principal: Principal | None = Depends(get_current_principal),
) -> None:
    """Apply role-aware rate limits (60 req/min for users, 20 req/min for guests)."""
    if principal is not None:
        await user_chat_limiter.check(principal.email)
    else:
        client_ip = get_client_ip(request)
        await guest_chat_limiter.check(client_ip)


@lru_cache(maxsize=1)
def get_document_parser() -> Any:
    """Return a cached, reusable PDF parser instance based on configuration."""
    if PARSER_TYPE == "llama":
        return create_drive_parser()
    if PARSER_TYPE == "pymupdf":
        return pymupdf_parser
    raise RuntimeError(f"Unsupported PARSER_TYPE configured: {PARSER_TYPE}")
