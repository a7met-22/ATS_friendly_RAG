"""Credential verification and extensible RBAC permission checks (DB + .env Bootstrap Admin)."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from security.passwords import verify_password
from security.permissions_catalog import (
    ALL_PERMISSION_CODES,
    PERMISSION_SYSTEM_SEARCH,
)
from security.users_repository import get_user_by_email

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "admin": ALL_PERMISSION_CODES,
    "system_search": ALL_PERMISSION_CODES,
    "recruiter": frozenset({PERMISSION_SYSTEM_SEARCH, "documents:write", "system:sync"}),
    "viewer": frozenset({PERMISSION_SYSTEM_SEARCH}),
}

_DUMMY_HASH = "pbkdf2_sha256$600000$AAAAAAAAAAAAAAAAAAAAAA==$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


@dataclass(frozen=True)
class Principal:
    email: str
    roles: frozenset[str]
    authenticated_at: datetime
    expires_at: datetime
    permissions: frozenset[str] = frozenset()
    full_name: str = ""
    user_id: int | None = None


@lru_cache(maxsize=1)
def _load_bootstrap_users() -> dict[str, dict[str, Any]]:
    """Load emergency/bootstrap admin accounts from AUTHORIZED_USERS_JSON."""
    raw = os.getenv("AUTHORIZED_USERS_JSON", "").strip()
    if not raw:
        return {}
    try:
        records = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("AUTHORIZED_USERS_JSON contains invalid JSON.") from exc
    if not isinstance(records, list):
        raise RuntimeError("AUTHORIZED_USERS_JSON must be a JSON array.")

    users: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        email = record.get("email")
        password_hash = record.get("password_hash")
        roles = record.get("roles", [])
        if not isinstance(email, str) or not isinstance(password_hash, str):
            continue
        if not isinstance(roles, list) or not all(isinstance(role, str) for role in roles):
            continue
        role_set = frozenset(roles)
        resolved_perms: set[str] = set()
        for r in role_set:
            resolved_perms.update(ROLE_PERMISSIONS.get(r, set()))
        users[email.strip().casefold()] = {
            "password_hash": password_hash,
            "roles": role_set,
            "permissions": frozenset(resolved_perms),
        }
    return users


def _build_principal(
    *,
    email: str,
    roles: frozenset[str],
    permissions: frozenset[str],
    full_name: str = "",
    user_id: int | None = None,
) -> Principal:
    now = datetime.now(timezone.utc)
    ttl_minutes = int(os.getenv("AUTH_SESSION_TTL_MINUTES", "60"))
    ttl_minutes = min(max(ttl_minutes, 5), 720)
    return Principal(
        email=email,
        roles=roles,
        authenticated_at=now,
        expires_at=now + timedelta(minutes=ttl_minutes),
        permissions=permissions,
        full_name=full_name,
        user_id=user_id,
    )


def authenticate(email: str, password: str) -> Principal | None:
    """Synchronous bootstrap verification."""
    normalized_email = email.strip().casefold() if isinstance(email, str) else ""
    if not normalized_email or not isinstance(password, str) or not password:
        return None

    user = _load_bootstrap_users().get(normalized_email)
    target_hash = user["password_hash"] if user is not None else _DUMMY_HASH
    try:
        is_valid = verify_password(password, target_hash)
    except Exception:
        is_valid = False

    if user is None or not is_valid:
        return None

    return _build_principal(
        email=normalized_email,
        roles=user["roles"],
        permissions=user["permissions"],
    )


async def authenticate_async(email: str, password: str) -> Principal | None:
    """Timing-safe async authentication checking PostgreSQL RBAC users first, then .env bootstrap."""
    normalized_email = email.strip().casefold() if isinstance(email, str) else ""
    if not normalized_email or not isinstance(password, str) or not password:
        return None

    db_user = await get_user_by_email(normalized_email, include_password_hash=True)
    if db_user is not None:
        target_hash = db_user["password_hash"]
        is_valid = await asyncio.to_thread(verify_password, password, target_hash)
        if not is_valid or not db_user["is_active"]:
            return None
        return _build_principal(
            email=db_user["email"],
            roles=frozenset({db_user["role_name"]}),
            permissions=db_user["permissions"],
            full_name=db_user["full_name"],
            user_id=db_user["id"],
        )

    return await asyncio.to_thread(authenticate, normalized_email, password)


def is_principal_active(principal: Principal | None) -> bool:
    """Fast in-memory expiry check."""
    return bool(
        principal
        and isinstance(principal, Principal)
        and datetime.now(timezone.utc) < principal.expires_at
    )


def has_permission(principal: Principal | None, permission: str) -> bool:
    """Check whether an active principal holds the requested permission code."""
    if not is_principal_active(principal):
        return False

    if permission in principal.permissions:
        return True

    for role in principal.roles:
        if permission in ROLE_PERMISSIONS.get(role, frozenset()):
            return True
    return False


def require_permission(principal: Principal | None, permission: str) -> None:
    """Raise PermissionError when the principal lacks the required permission."""
    if not has_permission(principal, permission):
        raise PermissionError("You are not authorized to access this resource.")
