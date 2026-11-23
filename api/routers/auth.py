"""Authentication router: credential verification, brute-force protection, and JWT issuance."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from api.dependencies import enforce_login_rate_limit, get_client_ip
from api.schemas import ErrorResponse, LoginRequest, LoginResponse
from api.security import DistributedRateLimiter, create_access_token
from security.authorization import authenticate_async

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
    summary="Authenticate user and issue a stateless JWT token",
)
async def login(body: LoginRequest, request: Request, response: Response) -> LoginResponse:
    """Verify credentials with IP + Account lockout and return a non-cacheable JWT."""
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"

    normalized_email = body.email.strip().casefold()
    client_ip = get_client_ip(request)
    lock_key = f"{normalized_email}:{client_ip}"

    await _account_ip_limiter.check(lock_key)

    principal = await authenticate_async(normalized_email, body.password)

    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password, or account is not authorized.",
        )

    # تصفير عداد المحاولات الفاشلة فور نجاح الدخول
    await _account_ip_limiter.reset(lock_key)

    access_token, expires_in = create_access_token(principal)

    return LoginResponse(
        access_token=access_token,
        expires_in_seconds=expires_in,
        email=principal.email,
        roles=sorted(principal.roles),
    )
