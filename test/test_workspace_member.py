"""Black-box E2E tests for workspace member management."""

from __future__ import annotations

import os
from uuid import UUID, uuid4

from pytest_steps import test_steps
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

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


def _register_and_create_workspace(
    email_prefix: str,
    user_name: str = "Workspace Owner",
    workspace_name: str = "Workspace Members",
) -> tuple[str, dict, str]:
    email, headers = _register_user(email_prefix, user_name)
    response = TestUtils.make_request(
        "POST",
        "/app/workspace",
        payload={"name": workspace_name},
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


def _get_user_key(user_email: str) -> str:
    session = _db_session()
    try:
        user = session.query(User).filter(User.email == user_email).first()
        assert user is not None
        return str(user.user_key)
    finally:
        session.close()


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


def _get_member_role(workspace_key: str, user_email: str) -> str | None:
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
        if membership is None or membership.role is None:
            return None
        return membership.role.name
    finally:
        session.close()


def _has_workspace_membership(workspace_key: str, user_email: str) -> bool:
    return _get_member_role(workspace_key, user_email) is not None


@test_steps("test_unauthorized_no_token", "test_unauthorized_bad_token")
def test_workspace_member_unauthorized_requests():
    response = TestUtils.make_request("GET", "/app/workspace/member")
    assert response.status_code == 401
    yield

    response = TestUtils.make_request(
        "PUT",
        "/app/workspace/member",
        payload={"user_key": str(uuid4()), "role_key": str(uuid4())},
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401
    yield


@test_steps("test_owner_list_contains_member_details", "test_member_can_list_same_workspace")
def test_workspace_member_list_happy_path():
    owner_email, owner_headers, workspace_key = _register_and_create_workspace(
        "workspace.member.list.owner",
        user_name="Owner List",
        workspace_name="Workspace Member List",
    )
    admin_email, admin_headers = _register_user("workspace.member.list.admin", "Admin List")
    member_email, member_headers = _register_user("workspace.member.list.member", "Member List")

    _add_workspace_member(workspace_key, admin_email, "admin")
    _add_workspace_member(workspace_key, member_email, "member")

    response = TestUtils.make_request(
        "GET",
        f"/app/workspace/member?workspace_key={workspace_key}",
        headers=owner_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)

    members_by_email = {item.get("email"): item for item in body}
    assert members_by_email[owner_email]["name"].startswith("Owner List-")
    assert members_by_email[owner_email]["role"] == "owner"
    assert members_by_email[owner_email]["user_key"] == _get_user_key(owner_email)
    assert members_by_email[admin_email]["role"] == "admin"
    assert members_by_email[member_email]["role"] == "member"
    yield

    response = TestUtils.make_request("GET", "/app/workspace/member", headers=member_headers)
    assert response.status_code == 200
    members_by_email = {item.get("email"): item for item in response.json()}
    assert set(members_by_email) == {owner_email, admin_email, member_email}
    yield


@test_steps("test_owner_can_update_role", "test_owner_can_revoke_membership")
def test_workspace_member_owner_manage_happy_path():
    _, owner_headers, workspace_key = _register_and_create_workspace(
        "workspace.member.owner.manage",
        user_name="Owner Manage",
        workspace_name="Workspace Member Manage",
    )
    member_email, _ = _register_user("workspace.member.owner.target", "Target Member")
    _add_workspace_member(workspace_key, member_email, "member")
    member_user_key = _get_user_key(member_email)

    response = TestUtils.make_request(
        "PUT",
        "/app/workspace/member",
        payload={
            "workspace_key": workspace_key,
            "user_key": member_user_key,
            "role_key": _get_role_key("admin"),
        },
        headers=owner_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body.get("email") == member_email
    assert body.get("role") == "admin"
    assert _get_member_role(workspace_key, member_email) == "admin"
    yield

    response = TestUtils.make_request(
        "DELETE",
        "/app/workspace/member",
        payload={
            "workspace_key": workspace_key,
            "user_key": member_user_key,
        },
        headers=owner_headers,
    )
    assert response.status_code == 204
    assert _has_workspace_membership(workspace_key, member_email) is False
    yield


@test_steps("test_admin_can_update_member", "test_admin_can_delete_member")
def test_workspace_member_admin_can_manage_non_owner_members():
    _, owner_headers, workspace_key = _register_and_create_workspace(
        "workspace.member.admin.manage",
        user_name="Admin Owner",
        workspace_name="Workspace Admin Manage",
    )
    admin_email, admin_headers = _register_user("workspace.member.admin.actor", "Admin Actor")
    member_email, _ = _register_user("workspace.member.admin.target", "Member Target")

    _add_workspace_member(workspace_key, admin_email, "admin")
    _add_workspace_member(workspace_key, member_email, "member")
    member_user_key = _get_user_key(member_email)

    response = TestUtils.make_request(
        "PUT",
        "/app/workspace/member",
        payload={
            "user_key": member_user_key,
            "role_key": _get_role_key("admin"),
        },
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json().get("role") == "admin"
    assert _get_member_role(workspace_key, member_email) == "admin"
    yield

    response = TestUtils.make_request(
        "DELETE",
        "/app/workspace/member",
        payload={"user_key": member_user_key},
        headers=admin_headers,
    )
    assert response.status_code == 204
    assert _has_workspace_membership(workspace_key, member_email) is False
    yield


@test_steps("test_member_list_allowed", "test_member_update_forbidden", "test_member_delete_forbidden")
def test_workspace_member_permission_rules():
    _, owner_headers, workspace_key = _register_and_create_workspace(
        "workspace.member.perm.owner",
        user_name="Permission Owner",
        workspace_name="Workspace Permissions",
    )
    member_email, member_headers = _register_user("workspace.member.perm.member", "Permission Member")
    target_email, _ = _register_user("workspace.member.perm.target", "Permission Target")

    _add_workspace_member(workspace_key, member_email, "member")
    _add_workspace_member(workspace_key, target_email, "member")
    target_user_key = _get_user_key(target_email)

    response = TestUtils.make_request("GET", "/app/workspace/member", headers=member_headers)
    assert response.status_code == 200
    assert any(item.get("email") == target_email for item in response.json())
    yield

    response = TestUtils.make_request(
        "PUT",
        "/app/workspace/member",
        payload={
            "user_key": target_user_key,
            "role_key": _get_role_key("admin"),
        },
        headers=member_headers,
    )
    assert response.status_code == 403
    yield

    response = TestUtils.make_request(
        "DELETE",
        "/app/workspace/member",
        payload={"user_key": target_user_key},
        headers=member_headers,
    )
    assert response.status_code == 403
    assert _has_workspace_membership(workspace_key, target_email) is True
    yield


@test_steps(
    "test_list_requires_workspace_key_when_multiple_workspaces",
    "test_update_requires_workspace_key_when_multiple_workspaces",
    "test_delete_requires_workspace_key_when_multiple_workspaces",
)
def test_workspace_member_multiple_workspace_inference_rules():
    _, owner_headers = _register_user("workspace.member.multi.owner", "Multi Owner")
    response = TestUtils.make_request(
        "POST",
        "/app/workspace",
        payload={"name": "Multi Workspace One"},
        headers=owner_headers,
    )
    assert response.status_code == 201
    workspace_key_one = response.json()["workspace_key"]

    response = TestUtils.make_request(
        "POST",
        "/app/workspace",
        payload={"name": "Multi Workspace Two"},
        headers=owner_headers,
    )
    assert response.status_code == 201

    target_email, _ = _register_user("workspace.member.multi.target", "Multi Target")
    _add_workspace_member(workspace_key_one, target_email, "member")
    target_user_key = _get_user_key(target_email)

    response = TestUtils.make_request("GET", "/app/workspace/member", headers=owner_headers)
    assert response.status_code == 400
    yield

    response = TestUtils.make_request(
        "PUT",
        "/app/workspace/member",
        payload={
            "user_key": target_user_key,
            "role_key": _get_role_key("admin"),
        },
        headers=owner_headers,
    )
    assert response.status_code == 400
    yield

    response = TestUtils.make_request(
        "DELETE",
        "/app/workspace/member",
        payload={"user_key": target_user_key},
        headers=owner_headers,
    )
    assert response.status_code == 400
    yield


@test_steps(
    "test_invalid_uuid_rejected",
    "test_owner_role_assignment_forbidden",
    "test_owner_membership_cannot_be_modified",
    "test_owner_membership_cannot_be_revoked",
)
def test_workspace_member_validation_and_owner_protection_rules():
    owner_email, owner_headers, workspace_key = _register_and_create_workspace(
        "workspace.member.owner.protect",
        user_name="Protected Owner",
        workspace_name="Workspace Owner Protection",
    )
    member_email, _ = _register_user("workspace.member.owner.protect.target", "Protected Target")
    _add_workspace_member(workspace_key, member_email, "member")

    response = TestUtils.make_request(
        "PUT",
        "/app/workspace/member",
        payload={
            "workspace_key": workspace_key,
            "user_key": "not-a-uuid",
            "role_key": _get_role_key("admin"),
        },
        headers=owner_headers,
    )
    assert response.status_code == 400
    yield

    response = TestUtils.make_request(
        "PUT",
        "/app/workspace/member",
        payload={
            "workspace_key": workspace_key,
            "user_key": _get_user_key(member_email),
            "role_key": _get_role_key("owner"),
        },
        headers=owner_headers,
    )
    assert response.status_code == 403
    yield

    response = TestUtils.make_request(
        "PUT",
        "/app/workspace/member",
        payload={
            "workspace_key": workspace_key,
            "user_key": _get_user_key(owner_email),
            "role_key": _get_role_key("admin"),
        },
        headers=owner_headers,
    )
    assert response.status_code == 403
    yield

    response = TestUtils.make_request(
        "DELETE",
        "/app/workspace/member",
        payload={
            "workspace_key": workspace_key,
            "user_key": _get_user_key(owner_email),
        },
        headers=owner_headers,
    )
    assert response.status_code == 403
    yield
