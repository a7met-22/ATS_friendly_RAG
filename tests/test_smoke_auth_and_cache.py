from __future__ import annotations

import json
import os
from fastapi.testclient import TestClient
from starlette.requests import Request


def _setup_real_bootstrap_admin(monkeypatch) -> tuple[str, str]:
    """Create a temporary PBKDF2-hashed admin account isolated via monkeypatch."""
    from security.passwords import hash_password
    from security.authorization import _load_bootstrap_users

    email = "real.admin@company.com"
    raw_password = "StrongPassword@2026!"
    monkeypatch.setenv(
        "AUTHORIZED_USERS_JSON",
        json.dumps(
            [
                {
                    "email": email,
                    "password_hash": hash_password(raw_password),
                    "roles": ["admin"],
                }
            ]
        ),
    )
    _load_bootstrap_users.cache_clear()
    return email, raw_password


def test_real_http_login_flow_and_jwt_profile(monkeypatch) -> None:
    """1. Full HTTP auth test: rejects bad password (401), issues JWT (200), reads /me."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("JWT_SECRET_KEY", "integration_test_secret_key_must_be_32_chars_min!!")

    import security.authorization as auth_mod
    import api.dependencies as dep_mod

    async def _no_db_user(*args, **kwargs):
        return None

    monkeypatch.setattr(auth_mod, "get_user_by_email", _no_db_user)
    monkeypatch.setattr(dep_mod, "get_user_by_email", _no_db_user)

    email, password = _setup_real_bootstrap_admin(monkeypatch)
    from api.main import app

    client = TestClient(app)

    bad_resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "WrongPassword123"},
    )
    assert bad_resp.status_code == 401

    ok_resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert ok_resp.status_code == 200, ok_resp.text
    data = ok_resp.json()
    assert data["email"] == email
    assert data["expires_in_seconds"] > 0
    token = data["access_token"]

    me_resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["authenticated"] is True
    assert me_data["user"]["email"] == email
    assert "admin:manage_users" in me_data["user"]["permissions"]


def test_real_http_rbac_blocks_unauthenticated_admin_access() -> None:
    """2. Real HTTP test: unauthenticated requests to RBAC admin routes return 401."""
    from api.main import app

    client = TestClient(app)
    resp = client.get("/api/v1/admin/roles")
    assert resp.status_code == 401


def test_real_http_chat_validation_rejects_invalid_mode() -> None:
    """3. Real HTTP test: Pydantic rejects unsupported retrieval_mode with 422."""
    from api.main import app

    client = TestClient(app)
    invalid_resp = client.post(
        "/api/v1/chat/ask/stream",
        json={"question": "Test", "retrieval_mode": "invalid_mode", "top_k": 5},
    )
    assert invalid_resp.status_code == 422


def test_client_ip_anti_spoofing_through_real_http_request(monkeypatch) -> None:
    """4. Anti-spoofing test: trusts rightmost internal proxy hop, ignores external header."""
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "true")
    from api.dependencies import get_client_ip

    req_proxy = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"x-forwarded-for", b"1.1.1.1, 95.10.20.30")],
            "client": ("172.19.0.6", 12345),
        }
    )
    assert get_client_ip(req_proxy) == "95.10.20.30"

    req_direct = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"x-forwarded-for", b"10.0.0.1")],
            "client": ("8.8.8.8", 12345),
        }
    )
    assert get_client_ip(req_direct) == "8.8.8.8"


def test_rag_cache_key_isolation_and_content_versioning() -> None:
    """5. Cache isolation test: guest vs system and document version invalidation."""
    from api.services.rag_cache import build_rag_cache_key

    k_guest = build_rag_cache_key(
        access_level="guest",
        document_ids=[1],
        retrieval_mode="semantic",
        top_k=5,
        question="Find Python developer",
    )
    k_system = build_rag_cache_key(
        access_level="system",
        document_ids=[1],
        retrieval_mode="semantic",
        top_k=5,
        question="Find Python developer",
    )
    assert k_guest != k_system

    k_v1 = build_rag_cache_key(
        access_level="system",
        document_ids=[1],
        document_versions=["1:hash_v1:100"],
        retrieval_mode="semantic",
        top_k=5,
        question="Find Python developer",
    )
    k_v2 = build_rag_cache_key(
        access_level="system",
        document_ids=[1],
        document_versions=["1:hash_v2:200"],
        retrieval_mode="semantic",
        top_k=5,
        question="Find Python developer",
    )
    assert k_v1 != k_v2
