"""FastAPI Dependency Injection: Authentication, Guest Sessions, RBAC, Rate Limits, and Parsers."""

from __future__ import annotations

import os
import re
import uuid
import ipaddress
from functools import lru_cache
from typing import Any, Callable

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.security import (
    decode_access_token,
    guest_chat_limiter,
    login_rate_limiter,
    user_chat_limiter,
)
from config.settings import PARSER_TYPE

from security.permissions_catalog import PERMISSION_SYSTEM_SEARCH, PERMISSION_SYSTEM_SYNC
from security.authorization import (
    Principal,
    _load_bootstrap_users,
    has_permission,
    is_principal_active,
)
from security.roles_repository import fetch_role_permissions


from security.users_repository import get_user_by_email



_bearer_scheme = HTTPBearer(auto_error=False)
_SESSION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{16,64}$")


def _parse_valid_ip(raw: str | None) -> str | None:
    if not raw:
        return None
    candidate = raw.strip()
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def _is_trusted_proxy_peer(peer_host: str | None) -> bool:
    if not peer_host:
        return False
    try:
        ip_obj = ipaddress.ip_address(peer_host.strip())
        return ip_obj.is_private or ip_obj.is_loopback
    except ValueError:
        return False


def get_client_ip(request: Request) -> str:
    """Extract client IP safely by verifying the immediate peer is a trusted internal proxy."""
    peer_host = request.client.host if request.client else None
    trust_proxy = os.getenv("TRUST_PROXY_HEADERS", "false").strip().lower() == "true"

    if trust_proxy and _is_trusted_proxy_peer(peer_host):
        # Take the right-most hop appended by our trusted Nginx gateway (never the spoofable left-most hop)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            rightmost_hop = forwarded_for.split(",")[-1]
            parsed = _parse_valid_ip(rightmost_hop)
            if parsed:
                return parsed

        real_ip = _parse_valid_ip(request.headers.get("X-Real-IP"))
        if real_ip:
            return real_ip

    return _parse_valid_ip(peer_host) or "unknown"

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
    """Return a cached, reusable PDF parser instance with lazy dependency loading."""
    if PARSER_TYPE == "llama":
        from parsingWays.llama_parsing import create_drive_parser

        return create_drive_parser()

    if PARSER_TYPE == "pymupdf":
        from parsingWays.pymupdf_parsing import parse_pdf_bytes

        return parse_pdf_bytes

    raise RuntimeError(f"Unsupported PARSER_TYPE configured: {PARSER_TYPE}")


def require_permission_dep(permission: str) -> Callable[..., Principal]:
    """Dependency factory enforcing that the authenticated user holds a specific RBAC permission."""

    def _dependency(
        principal: Principal | None = Depends(get_current_principal),
    ) -> Principal:
        if principal is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required to access this resource.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not has_permission(principal, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: '{permission}'.",
            )
        return principal

    return _dependency


# Reusable permission-bound dependencies (DRY aliases over require_permission_dep)
require_system_search_user = require_permission_dep(PERMISSION_SYSTEM_SEARCH)
require_drive_sync_user = require_permission_dep(PERMISSION_SYSTEM_SYNC)
