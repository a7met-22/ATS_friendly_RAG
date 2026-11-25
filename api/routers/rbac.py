"""Extensible Admin RBAC Router: Users, Custom Roles, and Permission Matrix management."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

from api.dependencies import get_client_ip, require_permission_dep
from api.security import DistributedRateLimiter
from security.authorization import Principal, _load_bootstrap_users
from security.permissions_catalog import (
    PERMISSION_CATALOG,
    PERMISSION_MANAGE_ROLES,
    PERMISSION_MANAGE_USERS,
)
from security.roles_repository import (
    create_role,
    delete_custom_role,
    list_roles,
    update_role,
)
from security.users_repository import create_user, list_users, update_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["RBAC Administration"])

_rbac_write_limiter = DistributedRateLimiter(
    bucket="admin_rbac_write",
    max_requests=25,
    window_seconds=60,
)


class CreateRoleRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=40, pattern=r"^[a-zA-Z0-9_-]+$")
    description: str = Field(default="", max_length=250)
    permissions: list[str] = Field(default_factory=list)


class UpdateRoleRequest(BaseModel):
    description: str | None = Field(default=None, max_length=250)
    permissions: list[str] = Field(default_factory=list)


class CreateUserRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=8, max_length=128)
    role_id: int = Field(..., gt=0)


class UpdateUserRequest(BaseModel):
    role_id: int | None = Field(default=None, gt=0)
    is_active: bool | None = None


@router.get("/permissions", summary="List all system permission codes for UI matrix")
async def get_permissions_catalog(
    _: Principal = Depends(require_permission_dep(PERMISSION_MANAGE_ROLES)),
) -> dict[str, Any]:
    return {"permissions": list(PERMISSION_CATALOG)}


@router.get("/roles", summary="List all roles and their allowed operations")
async def get_all_roles(
    _: Principal = Depends(require_permission_dep(PERMISSION_MANAGE_ROLES)),
) -> dict[str, Any]:
    roles = await list_roles()
    return {"roles": roles}


@router.post("/roles", status_code=status.HTTP_201_CREATED, summary="Create a new custom role")
async def add_new_role(
    request: Request,
    body: CreateRoleRequest,
    admin: Principal = Depends(require_permission_dep(PERMISSION_MANAGE_ROLES)),
) -> dict[str, Any]:
    await _rbac_write_limiter.check(get_client_ip(request))
    try:
        role = await create_role(body.name, body.description, body.permissions)
        logger.info("Admin %s created custom role '%s'", admin.email, role["name"])
        return {"role": role}
    except Exception as exc:
        if "unique" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A role with this name already exists.",
            ) from exc
        raise


@router.put("/roles/{role_id}", summary="Update allowed operations for a role")
async def modify_role_permissions(
    request: Request,
    role_id: int,
    body: UpdateRoleRequest,
    admin: Principal = Depends(require_permission_dep(PERMISSION_MANAGE_ROLES)),
) -> dict[str, Any]:
    await _rbac_write_limiter.check(get_client_ip(request))
    try:
        role = await update_role(role_id, body.description, body.permissions)
        logger.info("Admin %s updated permissions for role ID %s", admin.email, role_id)
        return {"role": role}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/roles/{role_id}", summary="Delete a custom non-system role")
async def remove_custom_role(
    request: Request,
    role_id: int,
    admin: Principal = Depends(require_permission_dep(PERMISSION_MANAGE_ROLES)),
) -> dict[str, str]:
    await _rbac_write_limiter.check(get_client_ip(request))
    try:
        await delete_custom_role(role_id)
        logger.info("Admin %s deleted custom role ID %s", admin.email, role_id)
        return {"status": "deleted"}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/users", summary="List all registered users")
async def get_all_users(
    _: Principal = Depends(require_permission_dep(PERMISSION_MANAGE_USERS)),
) -> dict[str, Any]:
    users = await list_users()
    return {"users": users}


@router.post("/users", status_code=status.HTTP_201_CREATED, summary="Register a new user and assign a role")
async def register_new_user(
    request: Request,
    body: CreateUserRequest,
    admin: Principal = Depends(require_permission_dep(PERMISSION_MANAGE_USERS)),
) -> dict[str, Any]:
    await _rbac_write_limiter.check(get_client_ip(request))

    normalized_email = body.email.strip().casefold()
    if normalized_email in _load_bootstrap_users():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email is reserved as a system bootstrap administrator.",
        )

    try:
        user = await create_user(normalized_email, body.full_name, body.password, body.role_id)
        logger.info("Admin %s registered new user '%s' with role_id=%s", admin.email, user["email"], body.role_id)
        return {"user": user}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        if "unique" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists.",
            ) from exc
        raise


@router.patch("/users/{user_id}", summary="Update user role or active status")
async def modify_user_access(
    request: Request,
    user_id: int,
    body: UpdateUserRequest,
    admin: Principal = Depends(require_permission_dep(PERMISSION_MANAGE_USERS)),
) -> dict[str, Any]:
    await _rbac_write_limiter.check(get_client_ip(request))

    if admin.user_id is not None and admin.user_id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot modify or deactivate your own active administrator account.",
        )

    try:
        user = await update_user(
            user_id,
            role_id=body.role_id,
            is_active=body.is_active,
            actor_email=admin.email,
        )
        logger.info("Admin %s updated user ID %s", admin.email, user_id)
        return {"user": user}
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
