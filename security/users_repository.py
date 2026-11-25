"""PostgreSQL repository for RBAC users with Redis profile caching."""

from __future__ import annotations

import asyncio
from typing import Any

from psycopg.rows import dict_row

from database_utilities.database_connection import get_connection
from security.passwords import hash_password
from security.rbac_cache import (
    get_cached_user_profile,
    invalidate_user_profile,
    set_cached_user_profile,
)
from security.roles_repository import fetch_role_permissions


async def get_user_by_email(email: str, *, include_password_hash: bool = False) -> dict[str, Any] | None:
    """Fetch a user record with role info and live permissions (Redis-cached for non-login checks)."""
    normalized = email.strip().casefold()

    if not include_password_hash:
        cached = await get_cached_user_profile(normalized)
        if cached is not None:
            cached["permissions"] = await fetch_role_permissions(cached["role_id"])
            return cached

    async with await get_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT u.id, u.email, u.full_name, u.password_hash, u.is_active,
                       r.id AS role_id, r.name AS role_name
                FROM public.users u
                JOIN public.roles r ON u.role_id = r.id
                WHERE lower(u.email) = %s
                """,
                (normalized,),
            )
            row = await cur.fetchone()
            if not row:
                return None

            user = dict(row)
            user["permissions"] = await fetch_role_permissions(user["role_id"])

            cache_safe_profile = {k: v for k, v in user.items() if k != "password_hash"}
            await set_cached_user_profile(normalized, cache_safe_profile)

            if not include_password_hash:
                return cache_safe_profile
            return user


async def list_users() -> list[dict[str, Any]]:
    """Return all registered users with their assigned role."""
    async with await get_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT u.id, u.email, u.full_name, u.is_active, u.created_at,
                       r.id AS role_id, r.name AS role_name
                FROM public.users u
                JOIN public.roles r ON u.role_id = r.id
                ORDER BY u.id ASC
                """
            )
            rows = await cur.fetchall()
            result = []
            for r in rows:
                item = dict(r)
                item["created_at"] = item["created_at"].isoformat()
                result.append(item)
            return result


async def create_user(email: str, full_name: str, password: str, role_id: int) -> dict[str, Any]:
    """Create a new user account with a PBKDF2 password hash (offloaded to thread pool)."""
    clean_email = email.strip().casefold()
    pw_hash = await asyncio.to_thread(hash_password, password)

    async with await get_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT name FROM public.roles WHERE id = %s", (role_id,))
                role = await cur.fetchone()
                if not role:
                    raise ValueError("Selected role does not exist.")

                await cur.execute(
                    """
                    INSERT INTO public.users (email, full_name, password_hash, role_id, is_active)
                    VALUES (%s, %s, %s, %s, TRUE)
                    RETURNING id, email, full_name, is_active, created_at
                    """,
                    (clean_email, full_name.strip(), pw_hash, role_id),
                )
                created_row = await cur.fetchone()
                assert created_row is not None
                user = dict(created_row)
                user["created_at"] = user["created_at"].isoformat()
                user["role_id"] = role_id
                user["role_name"] = role["name"]
                return user


async def update_user(
    user_id: int,
    *,
    role_id: int | None = None,
    is_active: bool | None = None,
    actor_email: str | None = None,
) -> dict[str, Any]:
    """Update a user's assigned role or activation status and invalidate Redis profile cache."""
    async with await get_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT id, email FROM public.users WHERE id = %s", (user_id,))
                existing = await cur.fetchone()
                if not existing:
                    raise ValueError("User not found.")

                if actor_email and existing["email"].strip().casefold() == actor_email.strip().casefold():
                    raise PermissionError("You cannot modify or deactivate your own active account.")

                if role_id is not None:
                    await cur.execute("SELECT 1 FROM public.roles WHERE id = %s", (role_id,))
                    if not await cur.fetchone():
                        raise ValueError("Selected role does not exist.")
                    await cur.execute(
                        "UPDATE public.users SET role_id = %s, updated_at = NOW() WHERE id = %s",
                        (role_id, user_id),
                    )
                if is_active is not None:
                    await cur.execute(
                        "UPDATE public.users SET is_active = %s, updated_at = NOW() WHERE id = %s",
                        (is_active, user_id),
                    )

    await invalidate_user_profile(existing["email"])

    users = await list_users()
    match = next((u for u in users if u["id"] == user_id), None)
    if not match:
        raise ValueError("User not found.")
    return match
