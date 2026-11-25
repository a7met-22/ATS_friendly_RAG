"""Authentication router: credential verification, brute-force protection, JWT issuance, and profile inspection."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from api.dependencies import (
    enforce_login_rate_limit,
    get_client_ip,
    get_current_principal,
)
from api.schemas import ErrorResponse, LoginRequest, LoginResponse
from api.security import DistributedRateLimiter, create_access_token
from security.authorization import Principal, authenticate_async

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])

_account_ip_limiter = DistributedRateLimiter(
    bucket="login_account_ip",
    max_requests=5,
    window_seconds=900,
)


@router.post(
    "/login",
    response_model=LoginResponse,
    dependencies=[Depends(enforce_login_rate_limit)],
    responses={
        401: {"model": ErrorResponse, "description": "Invalid credentials"},
        429: {"model": ErrorResponse, "description": "Too many login attempts"},
    },
    summary="Authenticate user and issue a signed JWT token",
)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
) -> LoginResponse:
    """Verify credentials (Database RBAC users or .env Bootstrap Admin) with dual-layer brute-force protection."""
    client_ip = get_client_ip(request)
    normalized_email = payload.email.strip().casefold()
    account_key = f"{normalized_email}:{client_ip}"

    await _account_ip_limiter.check(account_key)

    principal = await authenticate_async(normalized_email, payload.password)
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token, expires_in = create_access_token(principal)
    response.headers["Cache-Control"] = "no-store"

    return LoginResponse(
        access_token=token,
        expires_in_seconds=expires_in,
        email=principal.email,
        roles=sorted(principal.roles),
    )


@router.get(
    "/me",
    summary="Get current authenticated user profile and live permissions",
)
async def get_current_user_profile(
    principal: Principal | None = Depends(get_current_principal),
) -> dict:
    """Return current user profile, roles, and live RBAC permissions for the React frontend."""
    if principal is None:
        return {"authenticated": False, "user": None}

    return {
        "authenticated": True,
        "user": {
            "id": principal.user_id,
            "email": principal.email,
            "full_name": principal.full_name,
            "roles": sorted(principal.roles),
            "permissions": sorted(principal.permissions),
            "expires_at": principal.expires_at.isoformat(),
        },
    }
