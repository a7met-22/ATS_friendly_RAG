"""PostgreSQL repository for RBAC roles and permission mappings."""

from __future__ import annotations

from typing import Any
from psycopg.rows import dict_row

from database_utilities.database_connection import get_connection
from security.permissions_catalog import ALL_PERMISSION_CODES
from security.rbac_cache import (
    get_cached_role_permissions,
    invalidate_role_permissions,
    set_cached_role_permissions,
)


async def fetch_role_permissions(role_id: int) -> frozenset[str]:
    """Return allowed permission codes for a role (Redis-cached)."""
    cached = await get_cached_role_permissions(role_id)
    if cached is not None:
        return cached

    async with await get_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT permission_code FROM public.role_permissions WHERE role_id = %s",
                (role_id,),
            )
            rows = await cur.fetchall()
            perms = frozenset(r["permission_code"] for r in rows)

    await set_cached_role_permissions(role_id, perms)
    return perms


async def list_roles() -> list[dict[str, Any]]:
    """Return all roles along with their assigned permission codes."""
    async with await get_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT r.id, r.name, r.description, r.is_system,
                       COALESCE(array_agg(rp.permission_code ORDER BY rp.permission_code)
                                FILTER (WHERE rp.permission_code IS NOT NULL), '{}') AS permissions
                FROM public.roles r
                LEFT JOIN public.role_permissions rp ON r.id = rp.role_id
                GROUP BY r.id
                ORDER BY r.id ASC
                """
            )
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def create_role(name: str, description: str, permissions: list[str]) -> dict[str, Any]:
    """Create a new custom role with validated permissions."""
    clean_name = name.strip().lower()
    valid_perms = sorted(set(permissions) & ALL_PERMISSION_CODES)

    async with await get_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    INSERT INTO public.roles (name, description, is_system)
                    VALUES (%s, %s, FALSE)
                    RETURNING id, name, description, is_system
                    """,
                    (clean_name, description.strip()),
                )
                role = dict(await cur.fetchone())
                for code in valid_perms:
                    await cur.execute(
                        "INSERT INTO public.role_permissions (role_id, permission_code) VALUES (%s, %s)",
                        (role["id"], code),
                    )
                role["permissions"] = valid_perms
                return role


async def update_role(role_id: int, description: str | None, permissions: list[str]) -> dict[str, Any]:
    """Update a role's description and permission codes, then invalidate Redis cache."""
    valid_perms = sorted(set(permissions) & ALL_PERMISSION_CODES)

    async with await get_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT name FROM public.roles WHERE id = %s", (role_id,))
                existing = await cur.fetchone()
                if not existing:
                    raise ValueError("Role not found.")
                if existing["name"] == "admin":
                    valid_perms = sorted(ALL_PERMISSION_CODES)

                if description is not None:
                    await cur.execute(
                        "UPDATE public.roles SET description = %s, updated_at = NOW() WHERE id = %s",
                        (description.strip(), role_id),
                    )

                await cur.execute("DELETE FROM public.role_permissions WHERE role_id = %s", (role_id,))
                for code in valid_perms:
                    await cur.execute(
                        "INSERT INTO public.role_permissions (role_id, permission_code) VALUES (%s, %s)",
                        (role_id, code),
                    )

    await invalidate_role_permissions(role_id)
    roles = await list_roles()
    return next(r for r in roles if r["id"] == role_id)


async def delete_custom_role(role_id: int) -> None:
    """Delete a non-system role if no users are assigned to it."""
    async with await get_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT is_system FROM public.roles WHERE id = %s", (role_id,))
                role = await cur.fetchone()
                if not role:
                    raise ValueError("Role not found.")
                if role["is_system"]:
                    raise ValueError("Built-in system roles cannot be deleted.")

                await cur.execute("SELECT 1 FROM public.users WHERE role_id = %s LIMIT 1", (role_id,))
                if await cur.fetchone():
                    raise ValueError("Cannot delete a role that is currently assigned to users.")

                await cur.execute("DELETE FROM public.roles WHERE id = %s", (role_id,))

    await invalidate_role_permissions(role_id)
