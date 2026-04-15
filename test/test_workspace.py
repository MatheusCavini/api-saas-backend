"""Black-box E2E tests for workspace resource."""
from __future__ import annotations

import os
from unittest.mock import patch
from uuid import UUID, uuid4

from passlib.context import CryptContext
from pytest_steps import test_steps

from controllers.workspace import WorkspaceController
from models.api_key import ApiKey
from models.subscription import Subscription
from models.user import User
from models.workspace import Workspace
from models.workspace_member import WorkspaceMember
from test.test_api_key import (
    _db_session,
    _ensure_active_subscription_for_workspace,
)
from test.utils import TestUtils

_test_key_hasher = CryptContext(schemes=["argon2"], deprecated="auto")


def _insert_active_api_key_for_workspace(workspace_key: str) -> None:
    """Seed an active API key via DB (avoids Stripe on HTTP workspace delete)."""
    session = _db_session()
    try:
        ws = (
            session.query(Workspace)
            .filter(Workspace.workspace_key == UUID(workspace_key))
            .one()
        )
        plain = f"test-ws-del-{uuid4().hex}"
        api_key = ApiKey(
            workspace_id=ws.id,
            name="seeded-for-delete-test",
            key_prefix="sk_test_del",
            key_hash=_test_key_hasher.hash(plain),
            status="active",
        )
        session.add(api_key)
        session.commit()
    finally:
        session.close()


@test_steps("test_create_invalid", "test_create_valid", "test_list_member")
def test_workspace_create_and_list():
    """Validate workspace create schema and member list behavior."""
    email = f"workspace.{uuid4().hex}@test.com"
    headers = TestUtils.register_and_login(email, "Passw0rd!123", "Workspace Owner")

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
    headers = TestUtils.register_and_login(email, "Passw0rd!123", "Workspace Updater")

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
    """Owner can delete workspace (soft-deactivate, no Stripe subscription to cancel)."""
    email = f"workspace.delete.{uuid4().hex}@test.com"
    headers = TestUtils.register_and_login(email, "Passw0rd!123", "Workspace Deleter")

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

    session = _db_session()
    try:
        ws = (
            session.query(Workspace)
            .filter(Workspace.workspace_key == UUID(workspace_key))
            .one()
        )
        assert ws.deactivated_on is not None
        member_count = (
            session.query(WorkspaceMember)
            .filter(WorkspaceMember.workspace_id == ws.id)
            .count()
        )
        assert member_count == 1
    finally:
        session.close()
    yield


@test_steps("test_non_member_list", "test_non_member_update", "test_non_member_delete")
def test_workspace_access_non_member():
    """Non-members cannot update/delete; list returns empty array."""
    owner_email = f"workspace.owner.{uuid4().hex}@test.com"
    owner_headers = TestUtils.register_and_login(owner_email, "Passw0rd!123", "Workspace Owner")
    response = TestUtils.make_request("POST", "/app/workspace", payload={"name": "Workspace Owned"}, headers=owner_headers)
    assert response.status_code == 201
    workspace_key = response.json()["workspace_key"]

    other_email = f"workspace.other.{uuid4().hex}@test.com"
    other_headers = TestUtils.register_and_login(other_email, "Passw0rd!123", "Workspace Other")

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


@test_steps("test_delete_revokes_keys_delete", "test_delete_revokes_keys_confirm")
def test_workspace_delete_revokes_api_keys():
    """HTTP workspace delete revokes API keys (DB-seeded key; no subscription so Stripe is not called)."""
    email = f"workspace.del.keys.{uuid4().hex}@test.com"
    headers = TestUtils.register_and_login(email, "Passw0rd!123", "Workspace Key Deleter")

    response = TestUtils.make_request(
        "POST",
        "/app/workspace",
        payload={"name": "Workspace With Keys"},
        headers=headers,
    )
    assert response.status_code == 201
    workspace_key = response.json()["workspace_key"]

    _insert_active_api_key_for_workspace(workspace_key)

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

    session = _db_session()
    try:
        ws = (
            session.query(Workspace)
            .filter(Workspace.workspace_key == UUID(workspace_key))
            .one()
        )
        assert ws.deactivated_on is not None
        keys = session.query(ApiKey).filter(ApiKey.workspace_id == ws.id).all()
        assert len(keys) >= 1
        assert all(key.status == "revoked" for key in keys)
    finally:
        session.close()
    yield


@patch("controllers.stripe.stripe.Subscription.delete")
def test_workspace_delete_cancels_stripe_subscription(mock_subscription_delete):
    """With an active subscription row, delete cancels Stripe and marks the subscription canceled in DB."""
    prev_stripe_key = os.environ.get("STRIPE_SECRET_KEY")
    os.environ["STRIPE_SECRET_KEY"] = "sk_test_workspace_delete_e2e"

    email = f"workspace.del.stripe.{uuid4().hex}@test.com"
    headers = TestUtils.register_and_login(email, "Passw0rd!123", "Workspace Stripe Deleter")

    response = TestUtils.make_request(
        "POST",
        "/app/workspace",
        payload={"name": "Workspace Stripe Delete"},
        headers=headers,
    )
    assert response.status_code == 201
    workspace_key = response.json()["workspace_key"]
    _ensure_active_subscription_for_workspace(workspace_key)

    session = _db_session()
    try:
        user = session.query(User).filter(User.email == email).one()
        WorkspaceController(session).delete_for_user(user, workspace_key)
    finally:
        session.close()

    if prev_stripe_key is not None:
        os.environ["STRIPE_SECRET_KEY"] = prev_stripe_key
    else:
        os.environ.pop("STRIPE_SECRET_KEY", None)

    mock_subscription_delete.assert_called()

    session = _db_session()
    try:
        ws = (
            session.query(Workspace)
            .filter(Workspace.workspace_key == UUID(workspace_key))
            .one()
        )
        assert ws.deactivated_on is not None
        member_count = (
            session.query(WorkspaceMember)
            .filter(WorkspaceMember.workspace_id == ws.id)
            .count()
        )
        assert member_count == 1
        row = (
            session.query(Subscription)
            .filter(Subscription.workspace_id == ws.id)
            .one()
        )
        assert row.status == "canceled"
    finally:
        session.close()


@patch("controllers.stripe.stripe.Subscription.delete")
def test_workspace_delete_without_subscription_skips_stripe(mock_subscription_delete):
    """No subscription row means delete does not call Stripe."""
    email = f"workspace.del.nosub.{uuid4().hex}@test.com"
    headers = TestUtils.register_and_login(email, "Passw0rd!123", "No Sub Deleter")

    response = TestUtils.make_request(
        "POST",
        "/app/workspace",
        payload={"name": "Workspace No Sub"},
        headers=headers,
    )
    assert response.status_code == 201
    workspace_key = response.json()["workspace_key"]

    session = _db_session()
    try:
        user = session.query(User).filter(User.email == email).one()
        WorkspaceController(session).delete_for_user(user, workspace_key)
    finally:
        session.close()

    mock_subscription_delete.assert_not_called()
