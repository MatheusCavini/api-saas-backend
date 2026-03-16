"""Black-box E2E tests for user me resource."""
from __future__ import annotations

import os
from uuid import uuid4

from pytest_steps import test_steps

from test.utils import TestUtils


os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("JWT_ALGORITHM", "HS256")


def _register_and_login(email: str, password: str, name: str) -> dict:
    unique_name = f"{name}-{uuid4().hex}"
    payload = {"name": unique_name, "email": email, "password": password}
    response = TestUtils.make_request("POST", "/auth/register", payload=payload)
    assert response.status_code in (201, 409)

    response = TestUtils.make_request("POST", "/auth/login", payload={"email": email, "password": password})
    assert response.status_code == 200
    body = response.json()
    return {"Authorization": f"Bearer {body['access_token']}"}


@test_steps("test_unauthorized_no_token", "test_unauthorized_bad_token")
def test_user_me_unauthorized():
    """Requests without a valid Bearer token should be rejected."""
    response = TestUtils.make_request("GET", "/app/user/me")
    assert response.status_code == 401
    yield

    response = TestUtils.make_request(
        "GET",
        "/app/user/me",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401
    yield


@test_steps("test_me_no_workspace")
def test_user_me_no_workspace():
    """A new user without workspaces should be routed to create_workspace."""
    email = f"me.noworkspace.{uuid4().hex}@test.com"
    headers = _register_and_login(email, "Passw0rd!123", "No Workspace User")

    response = TestUtils.make_request("GET", "/app/user/me", headers=headers)
    assert response.status_code == 200
    
    body = response.json()
    assert "user" in body
    assert body["user"]["email"] == email
    
    assert "workspaces" in body
    assert body["workspaces"] == []
    
    assert body["routing_state"] == "create_workspace"
    yield


@test_steps("test_create_workspace", "test_me_with_workspace_no_sub")
def test_user_me_with_workspace_no_subscription():
    """A user with a workspace (and no active sub) should be routed to plan_selection."""
    email = f"me.workspace.{uuid4().hex}@test.com"
    headers = _register_and_login(email, "Passw0rd!123", "Workspace User")

    # Step 1: Create a workspace
    payload = {"name": "My Awesome Startup"}
    response = TestUtils.make_request("POST", "/app/workspace", payload=payload, headers=headers)
    assert response.status_code == 201
    yield

    # Step 2: Fetch /me and verify it dynamically routes them to the paywall
    response = TestUtils.make_request("GET", "/app/user/me", headers=headers)
    assert response.status_code == 200
    
    body = response.json()
    assert body["user"]["email"] == email
    assert len(body["workspaces"]) == 1
    
    # Verify the workspace mapper and role injection worked
    workspace = body["workspaces"][0]
    assert workspace["name"] == "My Awesome Startup"
    assert workspace["role"] == "owner"
    assert workspace.get("subscription_status") == "inactive"
    
    # Verify the fallback routing logic kicks in
    assert body["routing_state"] == "plan_selection"
    yield