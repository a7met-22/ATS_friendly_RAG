"""Credential verification and permission checks.

2. 
	• لو المهاجم جرب إيميل مش موجود (user is None)، الدالة هترجع None في 0.1 مللي ثانية. ولو جرب إيميل موجود فعلاً بس باسورد غلط، الدالة هتشغل verify_password وترجع None في 100 مللي ثانية. المهاجم يقدر يقيس فرق الوقت ده ويعرف مين الإيميلات المسجلة في نظامك!
	• الحل الأمني: بنعمل "تشفير وهمي" (Dummy Hash Verification) لو user is None عشان زمن الرد يكون متطابق في الحالتين.

Authorized users are provisioned through the AUTHORIZED_USERS_JSON environment
variable. Passwords are PBKDF2 hashes; plaintext passwords are never persisted.

Credential verification and permission checks (Async-ready & Timing-safe)."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from security.passwords import verify_password

PERMISSION_SYSTEM_SEARCH = "search_system_documents"
ROLE_PERMISSIONS = {
    "system_search": {PERMISSION_SYSTEM_SEARCH},
    "admin": {PERMISSION_SYSTEM_SEARCH},
}

# هاش وهمي يستخدم لمنع هجمات قياس الوقت (Timing Attacks) عندما يكون الإيميل غير موجود
_DUMMY_HASH = "pbkdf2_sha256$600000$AAAAAAAAAAAAAAAAAAAAAA==$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


@dataclass(frozen=True)
class Principal:
    email: str
    roles: frozenset[str]
    authenticated_at: datetime
    expires_at: datetime



@lru_cache(maxsize=1)
def _load_users() -> dict[str, dict[str, Any]]:
    """Load and cache authorized users once in memory."""
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
        users[email.strip().casefold()] = {
            "password_hash": password_hash,
            "roles": frozenset(roles),
        }
    return users


def authenticate(email: str, password: str) -> Principal | None:
    """Return a principal only when credentials match an authorized account (CPU-bound)."""
    normalized_email = email.strip().casefold() if isinstance(email, str) else ""
    if not normalized_email or not isinstance(password, str) or not password:
        return None

    user = _load_users().get(normalized_email)

    # الحماية ضد Timing Attacks: تنفيذ verify_password دائماً حتى لو المستخدم غير موجود
    target_hash = user["password_hash"] if user is not None else _DUMMY_HASH
    try:
        is_valid = verify_password(password, target_hash)
    except Exception:
        is_valid = False

    if user is None or not is_valid:
        return None

    now = datetime.now(timezone.utc)
    ttl_minutes = int(os.getenv("AUTH_SESSION_TTL_MINUTES", "60"))
    ttl_minutes = min(max(ttl_minutes, 5), 720)
    return Principal(
        email=normalized_email,
        roles=user["roles"],
        authenticated_at=now,
        expires_at=now + timedelta(minutes=ttl_minutes),
    )


async def authenticate_async(email: str, password: str) -> Principal | None:
    """Non-blocking authentication wrapper for FastAPI async endpoints."""
    return await asyncio.to_thread(authenticate, email, password)


def is_principal_active(principal: Principal | None) -> bool:
    """Fast in-memory check -> stays Sync."""
    return bool(
        principal
        and isinstance(principal, Principal)
        and datetime.now(timezone.utc) < principal.expires_at
    )


def has_permission(principal: Principal | None, permission: str) -> bool:
    """Fast in-memory check -> stays Sync."""
    if not is_principal_active(principal):
        return False
    granted = set()
    for role in principal.roles:
        granted.update(ROLE_PERMISSIONS.get(role, set()))
    return permission in granted


def require_permission(principal: Principal | None, permission: str) -> None:
    """Fast in-memory check -> stays Sync."""
    if not has_permission(principal, permission):
        raise PermissionError("You are not authorized to access this resource.")
