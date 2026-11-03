"""Credential verification and permission checks.

Authorized users are provisioned through the AUTHORIZED_USERS_JSON environment
variable. Passwords are PBKDF2 hashes; plaintext passwords are never persisted.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from security.passwords import verify_password

PERMISSION_SYSTEM_SEARCH = "search_system_documents"
ROLE_PERMISSIONS = {
    "system_search": {PERMISSION_SYSTEM_SEARCH},
    "admin": {PERMISSION_SYSTEM_SEARCH},
}


@dataclass(frozen=True)
class Principal:
    email: str
    roles: frozenset[str]
    authenticated_at: datetime
    expires_at: datetime


def _load_users() -> dict[str, dict[str, Any]]:
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
    """Return a principal only when credentials match an authorized account."""
    normalized_email = email.strip().casefold() if isinstance(email, str) else ""
    if not normalized_email or not isinstance(password, str) or not password:
        return None

    user = _load_users().get(normalized_email)
    if user is None or not verify_password(password, user["password_hash"]):
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


def is_principal_active(principal: Principal | None) -> bool:
    return bool(
        principal
        and isinstance(principal, Principal)
        and datetime.now(timezone.utc) < principal.expires_at
    )


def has_permission(principal: Principal | None, permission: str) -> bool:
    if not is_principal_active(principal):
        return False
    granted = set()
    for role in principal.roles:
        granted.update(ROLE_PERMISSIONS.get(role, set()))
    return permission in granted


def require_permission(principal: Principal | None, permission: str) -> None:
    if not has_permission(principal, permission):
        raise PermissionError("You are not authorized to access this resource.")
