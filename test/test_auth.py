"""Black-box E2E tests for authentication endpoints (email + password only)."""
from __future__ import annotations

import os
from uuid import UUID, uuid4

from pytest_steps import test_steps

from test.utils import TestUtils


os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("JWT_ALGORITHM", "HS256")

_REGISTER_EMAIL = f"auth.{uuid4().hex}@test.com"
_REGISTER_PASSWORD = "Passw0rd!123"
_REGISTER_NAME = "Auth Tester"

@test_steps("test_register_success", "test_register_duplicate_email", "test_register_missing_fields")
def test_register():
    """Validate register happy path, duplicate email, and missing fields."""
    payload = {"name": _REGISTER_NAME, "email": _REGISTER_EMAIL, "password": _REGISTER_PASSWORD}
    response = TestUtils.make_request("POST", "/auth/register", payload=payload)
    assert response.status_code == 201
    body = response.json()
    assert "access_token" in body
    assert body.get("token_type") == "Bearer"
    assert "user_key" in body
    yield

    response = TestUtils.make_request("POST", "/auth/register", payload=payload)
    assert response.status_code == 409
    yield

    response = TestUtils.make_request("POST", "/auth/register", payload={"email": _REGISTER_EMAIL})
    assert response.status_code == 400
    response = TestUtils.make_request("POST", "/auth/register", payload={"password": _REGISTER_PASSWORD})
    assert response.status_code == 400
    yield


@test_steps("test_login_success", "test_login_wrong_password", "test_login_nonexistent_email")
def test_login():
    """Validate login happy path and error cases."""
    payload = {"name": _REGISTER_NAME, "email": _REGISTER_EMAIL, "password": _REGISTER_PASSWORD}
    response = TestUtils.make_request("POST", "/auth/register", payload=payload)
    assert response.status_code in (201, 409)

    response = TestUtils.make_request(
        "POST",
        "/auth/login",
        payload={"email": _REGISTER_EMAIL, "password": _REGISTER_PASSWORD},
    )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body.get("token_type") == "Bearer"
    assert "user_key" in body

    token_payload = TestUtils.decode_token(body["access_token"])
    assert token_payload.get("sub") == body["user_key"]
    UUID(body["user_key"])
    yield

    response = TestUtils.make_request(
        "POST",
        "/auth/login",
        payload={"email": _REGISTER_EMAIL, "password": "WrongPass!123"},
    )
    assert response.status_code == 401
    yield

    response = TestUtils.make_request(
        "POST",
        "/auth/login",
        payload={"email": f"missing-{uuid4().hex}@test.local", "password": _REGISTER_PASSWORD},
    )
    assert response.status_code == 401
    yield
