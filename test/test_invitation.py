"""Black-box E2E tests for invitation resource."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

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


def _db_url() -> str:
    return os.environ.get(
        "TEST_DATABASE_URL",
        os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/api_db"),
    )


def _db_session():
    engine = create_engine(_db_url())
    Session = sessionmaker(bind=engine)
    return Session()


def _register_user(email_prefix: str, name: str) -> tuple[str, dict]:
    email = f"{email_prefix}.{uuid4().hex}@test.com"
    headers = TestUtils.register_and_login(email, "Passw0rd!123", name)
    return email, headers


def _register_and_create_workspace(email_prefix: str, name: str = "Invitation Owner") -> tuple[str, dict, str]:
    email, headers = _register_user(email_prefix, name)
    response = TestUtils.make_request(
        "POST",
        "/app/workspace",
        payload={"name": f"{name} Workspace"},
        headers=headers,
    )
    assert response.status_code == 201
    return email, headers, response.json()["workspace_key"]


def _get_role_key(role_name: str) -> str:
    session = _db_session()
    try:
        role = session.query(Role).filter(Role.name == role_name).first()
        assert role is not None
        return str(role.role_key)
    finally:
        session.close()


def _create_invitation(
    headers: dict,
    invited_email: str,
    role_name: str = "member",
    workspace_key: str | None = None,
):
    payload = {
        "invited_email": invited_email,
        "role_key": _get_role_key(role_name),
    }
    if workspace_key is not None:
        payload["workspace_key"] = workspace_key
    return TestUtils.make_request("POST", "/app/invitation", payload=payload, headers=headers)


def _add_workspace_member(workspace_key: str, user_email: str, role_name: str) -> None:
    session = _db_session()
    try:
        workspace = session.query(Workspace).filter(Workspace.workspace_key == UUID(workspace_key)).first()
        user = session.query(User).filter(User.email == user_email).first()
        role = session.query(Role).filter(Role.name == role_name).first()
        assert workspace is not None
        assert user is not None
        assert role is not None

        membership = (
            session.query(WorkspaceMember)
            .filter(WorkspaceMember.workspace_id == workspace.id)
            .filter(WorkspaceMember.user_id == user.id)
            .first()
        )
        if membership is None:
            membership = WorkspaceMember(
                workspace_id=workspace.id,
                user_id=user.id,
                role_id=role.id,
            )
            session.add(membership)
        else:
            membership.role_id = role.id
        session.commit()
    finally:
        session.close()


def _get_invitation_status_enum(invitation_key: str) -> str:
    session = _db_session()
    try:
        invitation = (
            session.query(Invitation)
            .filter(Invitation.invitation_key == UUID(invitation_key))
            .first()
        )
        assert invitation is not None
        status = session.query(InvitationStatus).filter(InvitationStatus.id == invitation.status_id).first()
        assert status is not None
        return status.enum
    finally:
        session.close()


def _has_workspace_membership(user_email: str, workspace_key: str) -> bool:
    session = _db_session()
    try:
        workspace = session.query(Workspace).filter(Workspace.workspace_key == UUID(workspace_key)).first()
        user = session.query(User).filter(User.email == user_email).first()
        assert workspace is not None
        assert user is not None
        membership = (
            session.query(WorkspaceMember)
            .filter(WorkspaceMember.workspace_id == workspace.id)
            .filter(WorkspaceMember.user_id == user.id)
            .first()
        )
        return membership is not None
    finally:
        session.close()


def _set_invitation_expires_at(invitation_key: str, expires_at: datetime) -> None:
    session = _db_session()
    try:
        invitation = (
            session.query(Invitation)
            .filter(Invitation.invitation_key == UUID(invitation_key))
            .first()
        )
        assert invitation is not None
        invitation.expires_at = expires_at
        session.commit()
    finally:
        session.close()


@test_steps("test_unauthorized_no_token", "test_unauthorized_bad_token")
def test_invitation_unauthorized_requests():
    response = TestUtils.make_request("GET", "/app/invitation")
    assert response.status_code == 401
    yield

    response = TestUtils.make_request(
        "POST",
        "/app/invitation/accept",
        payload={"invitation_key": str(uuid4())},
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401
    yield


@test_steps(
    "test_create_invalid_payload",
    "test_create_success",
    "test_list_contains_created_invitation",
    "test_revoke_success",
    "test_list_shows_revoked_status",
)
def test_invitation_create_list_and_revoke_happy_path():
    owner_email, owner_headers, workspace_key = _register_and_create_workspace("invitation.owner")
    invited_email = f"invite.new.{uuid4().hex}@test.com"

    response = TestUtils.make_request(
        "POST",
        "/app/invitation",
        payload={"invited_email": invited_email},
        headers=owner_headers,
    )
    assert response.status_code == 400
    yield

    response = _create_invitation(
        owner_headers,
        invited_email=invited_email,
        role_name="member",
        workspace_key=workspace_key,
    )
    assert response.status_code == 201
    body = response.json()
    assert body.get("invitation_key")
    assert body.get("invited_email") == invited_email
    assert body.get("workspace_key") == workspace_key
    assert body.get("host_user", {}).get("email") == owner_email
    assert body.get("role", {}).get("name") == "member"
    assert body.get("status", {}).get("enum") == "pending"
    assert body.get("expires_at")
    expires_at = datetime.fromisoformat(body["expires_at"])
    now = datetime.now(timezone.utc)
    assert now + timedelta(days=6, hours=23) < expires_at < now + timedelta(days=7, hours=1)
    assert "invited_user" not in body
    invitation_key = body["invitation_key"]
    yield

    response = TestUtils.make_request("GET", "/app/invitation", headers=owner_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    found = next((item for item in data if item.get("invitation_key") == invitation_key), None)
    assert found is not None
    assert found.get("status", {}).get("enum") == "pending"
    yield

    response = TestUtils.make_request(
        "DELETE",
        "/app/invitation",
        payload={"invitation_key": invitation_key},
        headers=owner_headers,
    )
    assert response.status_code == 204
    assert _get_invitation_status_enum(invitation_key) == "revoked"
    yield

    response = TestUtils.make_request("GET", "/app/invitation", headers=owner_headers)
    assert response.status_code == 200
    data = response.json()
    found = next((item for item in data if item.get("invitation_key") == invitation_key), None)
    assert found is not None
    assert found.get("status", {}).get("enum") == "revoked"
    yield


@test_steps("test_create_for_registered_user_returns_user_data")
def test_invitation_create_returns_existing_user_data():
    _, owner_headers, workspace_key = _register_and_create_workspace("invitation.registered.owner")
    invited_email, _ = _register_user("invitation.registered.target", "Invited Existing")

    response = _create_invitation(
        owner_headers,
        invited_email=invited_email,
        role_name="member",
        workspace_key=workspace_key,
    )
    assert response.status_code == 201
    body = response.json()
    assert body.get("invited_user", {}).get("email") == invited_email
    assert body.get("status", {}).get("enum") == "pending"
    yield


@test_steps(
    "test_create_rejects_existing_user_with_workspace",
    "test_create_rejects_duplicate_pending",
    "test_create_rejects_owner_role",
)
def test_invitation_create_unhappy_paths():
    _, owner_headers, workspace_key = _register_and_create_workspace("invitation.create.owner")
    existing_email, existing_headers = _register_user("invitation.create.member", "Existing Member")
    response = TestUtils.make_request(
        "POST",
        "/app/workspace",
        payload={"name": "Existing User Workspace"},
        headers=existing_headers,
    )
    assert response.status_code == 201

    response = _create_invitation(
        owner_headers,
        invited_email=existing_email,
        role_name="member",
        workspace_key=workspace_key,
    )
    assert response.status_code == 409
    yield

    duplicate_email = f"invite.duplicate.{uuid4().hex}@test.com"
    response = _create_invitation(
        owner_headers,
        invited_email=duplicate_email,
        role_name="member",
        workspace_key=workspace_key,
    )
    assert response.status_code == 201

    response = _create_invitation(
        owner_headers,
        invited_email=duplicate_email,
        role_name="member",
        workspace_key=workspace_key,
    )
    assert response.status_code == 409
    yield

    response = _create_invitation(
        owner_headers,
        invited_email=f"invite.owner.{uuid4().hex}@test.com",
        role_name="owner",
        workspace_key=workspace_key,
    )
    assert response.status_code == 403
    yield


@test_steps(
    "test_admin_can_create_and_list",
    "test_member_create_forbidden",
    "test_member_list_forbidden",
    "test_member_delete_forbidden",
)
def test_invitation_permission_rules():
    _, owner_headers, workspace_key = _register_and_create_workspace("invitation.perm.owner")
    admin_email, admin_headers = _register_user("invitation.perm.admin", "Admin User")
    member_email, member_headers = _register_user("invitation.perm.member", "Member User")

    _add_workspace_member(workspace_key, admin_email, "admin")
    _add_workspace_member(workspace_key, member_email, "member")

    response = _create_invitation(
        admin_headers,
        invited_email=f"invite.admin.{uuid4().hex}@test.com",
        role_name="member",
        workspace_key=workspace_key,
    )
    assert response.status_code == 201
    invitation_key = response.json()["invitation_key"]

    response = TestUtils.make_request("GET", "/app/invitation", headers=admin_headers)
    assert response.status_code == 200
    assert any(item.get("invitation_key") == invitation_key for item in response.json())
    yield

    response = _create_invitation(
        member_headers,
        invited_email=f"invite.member.forbidden.{uuid4().hex}@test.com",
        role_name="member",
        workspace_key=workspace_key,
    )
    assert response.status_code == 403
    yield

    response = TestUtils.make_request("GET", "/app/invitation", headers=member_headers)
    assert response.status_code == 403
    yield

    response = TestUtils.make_request(
        "DELETE",
        "/app/invitation",
        payload={"invitation_key": invitation_key},
        headers=member_headers,
    )
    assert response.status_code == 403
    yield


@test_steps("test_list_with_no_workspace_returns_404", "test_list_with_multiple_workspaces_returns_400")
def test_invitation_list_infers_workspace_from_authorized_user():
    _, headers = _register_user("invitation.list.noworkspace", "No Workspace")

    response = TestUtils.make_request("GET", "/app/invitation", headers=headers)
    assert response.status_code == 404
    yield

    response = TestUtils.make_request("POST", "/app/workspace", payload={"name": "WS One"}, headers=headers)
    assert response.status_code == 201
    response = TestUtils.make_request("POST", "/app/workspace", payload={"name": "WS Two"}, headers=headers)
    assert response.status_code == 201

    response = TestUtils.make_request("GET", "/app/invitation", headers=headers)
    assert response.status_code == 400
    yield


@test_steps("test_accept_success", "test_membership_created")
def test_invitation_accept_happy_path():
    _, owner_headers, workspace_key = _register_and_create_workspace("invitation.accept.owner")
    invited_email, invited_headers = _register_user("invitation.accept.target", "Accept Target")

    response = _create_invitation(
        owner_headers,
        invited_email=invited_email,
        role_name="member",
        workspace_key=workspace_key,
    )
    assert response.status_code == 201
    invitation_key = response.json()["invitation_key"]

    response = TestUtils.make_request(
        "POST",
        "/app/invitation/accept",
        payload={"invitation_key": invitation_key},
        headers=invited_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body.get("invitation_key") == invitation_key
    assert body.get("status", {}).get("enum") == "accepted"
    assert body.get("invited_user", {}).get("email") == invited_email
    yield

    assert _get_invitation_status_enum(invitation_key) == "accepted"
    assert _has_workspace_membership(invited_email, workspace_key) is True
    yield


@test_steps("test_refuse_success", "test_no_membership_created")
def test_invitation_refuse_happy_path():
    _, owner_headers, workspace_key = _register_and_create_workspace("invitation.refuse.owner")
    invited_email, invited_headers = _register_user("invitation.refuse.target", "Refuse Target")

    response = _create_invitation(
        owner_headers,
        invited_email=invited_email,
        role_name="member",
        workspace_key=workspace_key,
    )
    assert response.status_code == 201
    invitation_key = response.json()["invitation_key"]

    response = TestUtils.make_request(
        "POST",
        "/app/invitation/refuse",
        payload={"invitation_key": invitation_key},
        headers=invited_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body.get("status", {}).get("enum") == "refused"
    assert body.get("invited_user", {}).get("email") == invited_email
    yield

    assert _get_invitation_status_enum(invitation_key) == "refused"
    assert _has_workspace_membership(invited_email, workspace_key) is False
    yield


@test_steps(
    "test_create_sets_one_week_expiration",
    "test_list_marks_expired",
    "test_accept_expired_rejected",
    "test_refuse_expired_rejected",
    "test_revoke_expired_rejected",
)
def test_invitation_expiration_handling():
    _, owner_headers, workspace_key = _register_and_create_workspace("invitation.expiry.owner")

    response = _create_invitation(
        owner_headers,
        invited_email=f"invite.expiry.window.{uuid4().hex}@test.com",
        role_name="member",
        workspace_key=workspace_key,
    )
    assert response.status_code == 201
    body = response.json()
    expires_at = datetime.fromisoformat(body["expires_at"])
    now = datetime.now(timezone.utc)
    assert now + timedelta(days=6, hours=23) < expires_at < now + timedelta(days=7, hours=1)
    yield

    response = _create_invitation(
        owner_headers,
        invited_email=f"invite.expiry.list.{uuid4().hex}@test.com",
        role_name="member",
        workspace_key=workspace_key,
    )
    assert response.status_code == 201
    expired_list_invitation_key = response.json()["invitation_key"]
    _set_invitation_expires_at(expired_list_invitation_key, datetime.now(timezone.utc) - timedelta(minutes=5))

    response = TestUtils.make_request("GET", "/app/invitation", headers=owner_headers)
    assert response.status_code == 200
    found = next((item for item in response.json() if item.get("invitation_key") == expired_list_invitation_key), None)
    assert found is not None
    assert found.get("status", {}).get("enum") == "expired"
    assert _get_invitation_status_enum(expired_list_invitation_key) == "expired"
    yield

    accept_email, accept_headers = _register_user("invitation.expiry.accept", "Expired Accept")
    response = _create_invitation(
        owner_headers,
        invited_email=accept_email,
        role_name="member",
        workspace_key=workspace_key,
    )
    assert response.status_code == 201
    expired_accept_invitation_key = response.json()["invitation_key"]
    _set_invitation_expires_at(expired_accept_invitation_key, datetime.now(timezone.utc) - timedelta(minutes=5))

    response = TestUtils.make_request(
        "POST",
        "/app/invitation/accept",
        payload={"invitation_key": expired_accept_invitation_key},
        headers=accept_headers,
    )
    assert response.status_code == 409
    assert response.json().get("message") == "Invitation has expired."
    assert _get_invitation_status_enum(expired_accept_invitation_key) == "expired"
    yield

    refuse_email, refuse_headers = _register_user("invitation.expiry.refuse", "Expired Refuse")
    response = _create_invitation(
        owner_headers,
        invited_email=refuse_email,
        role_name="member",
        workspace_key=workspace_key,
    )
    assert response.status_code == 201
    expired_refuse_invitation_key = response.json()["invitation_key"]
    _set_invitation_expires_at(expired_refuse_invitation_key, datetime.now(timezone.utc) - timedelta(minutes=5))

    response = TestUtils.make_request(
        "POST",
        "/app/invitation/refuse",
        payload={"invitation_key": expired_refuse_invitation_key},
        headers=refuse_headers,
    )
    assert response.status_code == 409
    assert response.json().get("message") == "Invitation has expired."
    assert _get_invitation_status_enum(expired_refuse_invitation_key) == "expired"
    yield

    response = _create_invitation(
        owner_headers,
        invited_email=f"invite.expiry.delete.{uuid4().hex}@test.com",
        role_name="member",
        workspace_key=workspace_key,
    )
    assert response.status_code == 201
    expired_delete_invitation_key = response.json()["invitation_key"]
    _set_invitation_expires_at(expired_delete_invitation_key, datetime.now(timezone.utc) - timedelta(minutes=5))

    response = TestUtils.make_request(
        "DELETE",
        "/app/invitation",
        payload={"invitation_key": expired_delete_invitation_key},
        headers=owner_headers,
    )
    assert response.status_code == 409
    assert response.json().get("message") == "Invitation has expired."
    assert _get_invitation_status_enum(expired_delete_invitation_key) == "expired"
    yield


@test_steps(
    "test_accept_wrong_user_forbidden",
    "test_accept_existing_workspace_member_conflict",
    "test_accept_invalid_uuid_rejected",
    "test_refuse_non_pending_rejected",
)
def test_invitation_action_unhappy_paths():
    _, owner_headers, workspace_key = _register_and_create_workspace("invitation.action.owner")
    invited_email = f"invite.action.{uuid4().hex}@test.com"
    _, wrong_user_headers = _register_user("invitation.action.wrong", "Wrong User")

    response = _create_invitation(
        owner_headers,
        invited_email=invited_email,
        role_name="member",
        workspace_key=workspace_key,
    )
    assert response.status_code == 201
    wrong_user_invitation_key = response.json()["invitation_key"]

    response = TestUtils.make_request(
        "POST",
        "/app/invitation/accept",
        payload={"invitation_key": wrong_user_invitation_key},
        headers=wrong_user_headers,
    )
    assert response.status_code == 403
    yield

    future_member_email = f"invite.futuremember.{uuid4().hex}@test.com"
    response = _create_invitation(
        owner_headers,
        invited_email=future_member_email,
        role_name="member",
        workspace_key=workspace_key,
    )
    assert response.status_code == 201
    future_member_invitation_key = response.json()["invitation_key"]

    future_member_headers = TestUtils.register_and_login(
        future_member_email,
        "Passw0rd!123",
        "Future Member",
    )
    response = TestUtils.make_request(
        "POST",
        "/app/workspace",
        payload={"name": "Future Member Workspace"},
        headers=future_member_headers,
    )
    assert response.status_code == 201

    response = TestUtils.make_request(
        "POST",
        "/app/invitation/accept",
        payload={"invitation_key": future_member_invitation_key},
        headers=future_member_headers,
    )
    assert response.status_code == 409
    yield

    response = TestUtils.make_request(
        "POST",
        "/app/invitation/accept",
        payload={"invitation_key": "not-a-uuid"},
        headers=wrong_user_headers,
    )
    assert response.status_code == 400
    yield

    refused_email, refused_headers = _register_user("invitation.action.refuse", "Already Refused")
    response = _create_invitation(
        owner_headers,
        invited_email=refused_email,
        role_name="member",
        workspace_key=workspace_key,
    )
    assert response.status_code == 201
    refused_invitation_key = response.json()["invitation_key"]

    response = TestUtils.make_request(
        "POST",
        "/app/invitation/refuse",
        payload={"invitation_key": refused_invitation_key},
        headers=refused_headers,
    )
    assert response.status_code == 200

    response = TestUtils.make_request(
        "POST",
        "/app/invitation/refuse",
        payload={"invitation_key": refused_invitation_key},
        headers=refused_headers,
    )
    assert response.status_code == 409
    yield
