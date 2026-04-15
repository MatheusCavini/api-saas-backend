"""Black-box E2E tests for user me resource."""
from __future__ import annotations

import os
from uuid import UUID
from uuid import uuid4

from pytest_steps import test_steps
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.invitation import Invitation
from models.invitation_status import InvitationStatus
from models.role import Role
from models.user import User
from models.workspace import Workspace
from models.workspace_member import WorkspaceMember
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


def _db_url() -> str:
    return os.environ.get(
        "TEST_DATABASE_URL",
        os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/api_db"),
    )


def _db_session():
    engine = create_engine(_db_url())
    Session = sessionmaker(bind=engine)
    return Session()


def _create_second_owner_membership(workspace_key: str, user_email: str) -> None:
    session = _db_session()
    try:
        workspace = session.query(Workspace).filter(Workspace.workspace_key == UUID(workspace_key)).one()
        user = session.query(User).filter(User.email == user_email).one()
        owner_role = session.query(Role).filter(Role.name == "owner").one()
        membership = (
            session.query(WorkspaceMember)
            .filter(WorkspaceMember.workspace_id == workspace.id)
            .filter(WorkspaceMember.user_id == user.id)
            .first()
        )
        if membership is None:
            session.add(
                WorkspaceMember(
                    workspace_id=workspace.id,
                    user_id=user.id,
                    role_id=owner_role.id,
                )
            )
        else:
            membership.role_id = owner_role.id
        session.commit()
    finally:
        session.close()


def _create_pending_invitation_for_email(workspace_key: str, host_email: str, invited_email: str) -> str:
    session = _db_session()
    try:
        workspace = session.query(Workspace).filter(Workspace.workspace_key == UUID(workspace_key)).one()
        host_user = session.query(User).filter(User.email == host_email).one()
        member_role = session.query(Role).filter(Role.name == "member").one()
        pending_status = session.query(InvitationStatus).filter(InvitationStatus.enum == "pending").one()
        invitation = Invitation(
            workspace_id=workspace.id,
            invited_email=invited_email,
            host_user_id=host_user.id,
            role_id=member_role.id,
            status_id=pending_status.id,
            expires_at=workspace.created_at,
        )
        session.add(invitation)
        session.commit()
        session.refresh(invitation)
        return str(invitation.invitation_key)
    finally:
        session.close()


def _get_user_by_original_email(original_email: str) -> User | None:
    session = _db_session()
    try:
        return session.query(User).filter(User.email == original_email).first()
    finally:
        session.close()


def _get_user_by_id(user_id: int) -> User:
    session = _db_session()
    try:
        return session.query(User).filter(User.id == user_id).one()
    finally:
        session.close()


def _membership_count_for_user_id(user_id: int) -> int:
    session = _db_session()
    try:
        return session.query(WorkspaceMember).filter(WorkspaceMember.user_id == user_id).count()
    finally:
        session.close()


def _get_invitation_status(invitation_key: str) -> str:
    session = _db_session()
    try:
        invitation = session.query(Invitation).filter(Invitation.invitation_key == UUID(invitation_key)).one()
        status = session.query(InvitationStatus).filter(InvitationStatus.id == invitation.status_id).one()
        return status.enum
    finally:
        session.close()


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

@test_steps("test_register", "test_update_username", "test_get_me")
def test_update_user():
    email = f"me.workspace.{uuid4().hex}@test.com"
    headers = _register_and_login(email, "Passw0rd!123", "Old Username")
    yield

    payload = {"name": "New Username"}
    response = TestUtils.make_request("PUT", "/app/user/me", payload=payload, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == payload.get("name")
    yield

    response = TestUtils.make_request("GET", "/app/user/me", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert "user" in body
    assert body["user"]["username"] == payload.get("name")
    yield


@test_steps("test_delete_unauthorized_no_token", "test_delete_unauthorized_bad_token")
def test_user_delete_unauthorized():
    response = TestUtils.make_request("DELETE", "/app/user/me")
    assert response.status_code == 401
    yield

    response = TestUtils.make_request(
        "DELETE",
        "/app/user/me",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401
    yield


@test_steps("test_delete_blocked_for_sole_owner")
def test_user_delete_rejects_sole_owner():
    email = f"me.delete.sole.{uuid4().hex}@test.com"
    headers = _register_and_login(email, "Passw0rd!123", "Sole Owner")

    response = TestUtils.make_request(
        "POST",
        "/app/workspace",
        payload={"name": "Protected Workspace"},
        headers=headers,
    )
    assert response.status_code == 201

    response = TestUtils.make_request("DELETE", "/app/user/me", headers=headers)
    assert response.status_code == 409
    assert "Transfer ownership or delete the workspace first." in response.json().get("message", "")

    response = TestUtils.make_request("GET", "/app/workspace", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    yield


@test_steps(
    "test_delete_account_success",
    "test_old_token_rejected_and_db_anonymized",
)
def test_user_delete_revokes_memberships_and_anonymizes():
    email = f"me.delete.success.{uuid4().hex}@test.com"
    headers = _register_and_login(email, "Passw0rd!123", "Delete Target")

    response = TestUtils.make_request(
        "POST",
        "/app/workspace",
        payload={"name": "Delete Target Workspace"},
        headers=headers,
    )
    assert response.status_code == 201
    workspace_key = response.json()["workspace_key"]

    second_owner_email = f"me.delete.coowner.{uuid4().hex}@test.com"
    _register_and_login(second_owner_email, "Passw0rd!123", "Co Owner")
    _create_second_owner_membership(workspace_key, second_owner_email)

    host_email = f"me.delete.host.{uuid4().hex}@test.com"
    host_headers = _register_and_login(host_email, "Passw0rd!123", "Invitation Host")
    host_workspace_response = TestUtils.make_request(
        "POST",
        "/app/workspace",
        payload={"name": "Host Workspace"},
        headers=host_headers,
    )
    assert host_workspace_response.status_code == 201
    invitation_key = _create_pending_invitation_for_email(
        host_workspace_response.json()["workspace_key"],
        host_email,
        email,
    )

    deleted_user_before = _get_user_by_original_email(email)
    assert deleted_user_before is not None
    deleted_user_id = deleted_user_before.id
    deleted_user_key = str(deleted_user_before.user_key)
    assert _membership_count_for_user_id(deleted_user_id) == 1
    assert _get_invitation_status(invitation_key) == "pending"

    response = TestUtils.make_request("DELETE", "/app/user/me", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["session_revoked"] is True
    assert "destroy the current session token" in body["message"]
    yield

    response = TestUtils.make_request("GET", "/app/user/me", headers=headers)
    assert response.status_code == 401

    deleted_user = _get_user_by_id(deleted_user_id)
    assert str(deleted_user.user_key) != deleted_user_key
    assert deleted_user.email == f"deleted_{deleted_user_id}@example.com"
    assert deleted_user.username == f"Deleted User {deleted_user_id}"
    assert deleted_user.password_hash.startswith(f"deleted-user-{deleted_user_id}-")
    assert deleted_user.deactivated_on is not None
    assert _membership_count_for_user_id(deleted_user_id) == 0
    assert _get_invitation_status(invitation_key) == "revoked"
    yield
