"""Black-box E2E tests for workspace resource."""
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


@test_steps("test_create_invalid", "test_create_valid", "test_list_member")
def test_workspace_create_and_list():
    """Validate workspace create schema and member list behavior."""
    email = f"workspace.{uuid4().hex}@test.com"
    headers = _register_and_login(email, "Passw0rd!123", "Workspace Owner")

    response = TestUtils.make_request("POST", "/app/workspace", payload={"wrong": "data"}, headers=headers)
    assert response.status_code == 400
    yield

    payload = {"name": "Workspace One"}
    response = TestUtils.make_request("POST", "/app/workspace", payload=payload, headers=headers)
    assert response.status_code == 201
    body = response.json()
    assert body.get("name") == "Workspace One"
    assert body.get("workspace_key")
    workspace_key = body["workspace_key"]
    yield

    response = TestUtils.make_request("GET", "/app/workspace", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert any(item.get("workspace_key") == workspace_key for item in data)
    yield


@test_steps("test_update_missing_name", "test_update_owner", "test_update_confirm")
def test_workspace_update_owner():
    """Owner can update workspace name; missing name is rejected."""
    email = f"workspace.update.{uuid4().hex}@test.com"
    headers = _register_and_login(email, "Passw0rd!123", "Workspace Updater")

    response = TestUtils.make_request("POST", "/app/workspace", payload={"name": "Workspace Update"}, headers=headers)
    assert response.status_code == 201
    body = response.json()
    workspace_key = body["workspace_key"]

    response = TestUtils.make_request("PUT", "/app/workspace", payload={}, headers=headers)
    assert response.status_code == 400
    yield

    response = TestUtils.make_request(
        "PUT",
        "/app/workspace",
        payload={"name": "Workspace Updated"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json().get("name") == "Workspace Updated"
    yield

    response = TestUtils.make_request("GET", "/app/workspace", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert any(item.get("workspace_key") == workspace_key and item.get("name") == "Workspace Updated" for item in data)
    yield


@test_steps("test_delete_owner", "test_delete_confirm")
def test_workspace_delete_owner():
    """Owner can delete workspace."""
    email = f"workspace.delete.{uuid4().hex}@test.com"
    headers = _register_and_login(email, "Passw0rd!123", "Workspace Deleter")

    response = TestUtils.make_request("POST", "/app/workspace", payload={"name": "Workspace Delete"}, headers=headers)
    assert response.status_code == 201
    workspace_key = response.json()["workspace_key"]

    response = TestUtils.make_request(
        "DELETE",
        "/app/workspace",
        payload={"workspace_key": workspace_key},
        headers=headers,
    )
    assert response.status_code == 204
    yield

    response = TestUtils.make_request("GET", "/app/workspace", headers=headers)
    assert response.status_code == 200
    assert response.json() == []
    yield


@test_steps("test_non_member_list", "test_non_member_update", "test_non_member_delete")
def test_workspace_access_non_member():
    """Non-members cannot update/delete; list returns empty array."""
    owner_email = f"workspace.owner.{uuid4().hex}@test.com"
    owner_headers = _register_and_login(owner_email, "Passw0rd!123", "Workspace Owner")
    response = TestUtils.make_request("POST", "/app/workspace", payload={"name": "Workspace Owned"}, headers=owner_headers)
    assert response.status_code == 201
    workspace_key = response.json()["workspace_key"]

    other_email = f"workspace.other.{uuid4().hex}@test.com"
    other_headers = _register_and_login(other_email, "Passw0rd!123", "Workspace Other")

    response = TestUtils.make_request("GET", "/app/workspace", headers=other_headers)
    assert response.status_code == 200
    assert response.json() == []
    yield

    response = TestUtils.make_request(
        "PUT",
        "/app/workspace",
        payload={"name": "Nope", "workspace_key": workspace_key},
        headers=other_headers,
    )
    assert response.status_code == 404
    yield

    response = TestUtils.make_request(
        "DELETE",
        "/app/workspace",
        payload={"workspace_key": workspace_key},
        headers=other_headers,
    )
    assert response.status_code == 404
    yield


@test_steps("test_unauthorized_no_token", "test_unauthorized_bad_token")
def test_workspace_unauthorized_requests():
    """Requests without a valid Bearer token should be rejected."""
    response = TestUtils.make_request("GET", "/app/workspace")
    assert response.status_code == 401
    yield

    response = TestUtils.make_request(
        "GET",
        "/app/workspace",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401
    yield
