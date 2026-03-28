"""Black-box E2E tests for API key resource."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from pytest_steps import test_steps

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.plan import Plan
from models.subscription import Subscription
from models.workspace import Workspace
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


def _ensure_active_subscription_for_workspace(workspace_key: str) -> None:
    session = _db_session()
    try:
        ws = session.query(Workspace).filter(Workspace.workspace_key == UUID(workspace_key)).first()
        assert ws is not None

        plan = session.query(Plan).filter(Plan.is_active.is_(True)).order_by(Plan.created_at.desc()).first()
        if plan is None:
            plan = Plan(
                name="E2E Plan",
                description="E2E plan for API key tests",
                price_cents=1000,
                currency="USD",
                rate_limit_rpm=60,
                features=["Feature 1"],
                monthly_quota=1000,
                stripe_price_id=f"price_test_{uuid4().hex}",
                is_active=True,
            )
            session.add(plan)
            session.commit()
            session.refresh(plan)

        subscription = Subscription(
            workspace_id=ws.id,
            plan_id=plan.id,
            stripe_sub_id=f"sub_test_{uuid4().hex}",
            status="active",
            current_period_end=datetime.now(timezone.utc) + timedelta(days=30),
        )
        session.add(subscription)
        session.commit()
    finally:
        session.close()


def _register_login_and_create_workspace(email_prefix: str) -> dict:
    email = f"{email_prefix}.{uuid4().hex}@test.com"
    headers = TestUtils.register_and_login(email, "Passw0rd!123", "ApiKey User")
    response = TestUtils.make_request(
        "POST",
        "/app/workspace",
        payload={"name": "ApiKey Workspace"},
        headers=headers,
    )
    assert response.status_code == 201
    return headers


@test_steps("test_unauthorized_no_token", "test_unauthorized_bad_token")
def test_api_key_unauthorized_requests():
    response = TestUtils.make_request("POST", "/app/api-key", payload={})
    assert response.status_code == 401
    yield

    response = TestUtils.make_request(
        "POST",
        "/app/api-key",
        payload={},
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401
    yield


@test_steps("test_create_requires_workspace", "test_create_success", "test_get_does_not_leak_plaintext_or_hash")
def test_api_key_create_and_get_happy_path():
    email = f"api_key.noworkspace.{uuid4().hex}@test.com"
    headers = TestUtils.register_and_login(email, "Passw0rd!123", "No Workspace")

    response = TestUtils.make_request("POST", "/app/api-key", payload={}, headers=headers)
    assert response.status_code == 404
    yield

    response = TestUtils.make_request("POST", "/app/workspace", payload={"name": "Key WS"}, headers=headers)
    assert response.status_code == 201
    workspace_key = response.json()["workspace_key"]

    response = TestUtils.make_request("POST", "/app/api-key", payload={}, headers=headers)
    assert response.status_code == 403

    _ensure_active_subscription_for_workspace(workspace_key)

    response = TestUtils.make_request("POST", "/app/api-key", payload={}, headers=headers)
    assert response.status_code == 201
    body = response.json()

    assert body.get("api_key_key")
    UUID(body["api_key_key"])
    api_key_key = body["api_key_key"]

    assert body.get("plain_text_key")
    assert isinstance(body["plain_text_key"], str)
    assert body["plain_text_key"].startswith("sk_live_")
    assert "key_hash" not in body

    assert body.get("key_prefix")
    assert body["key_prefix"].endswith("...")
    assert body["plain_text_key"].startswith(body["key_prefix"].replace("...", ""))
    yield

    response = TestUtils.make_request("GET", f"/app/api-key/{api_key_key}", headers=headers)
    assert response.status_code == 200
    get_body = response.json()
    assert get_body.get("api_key_key") == api_key_key
    assert get_body.get("key_prefix") == body["key_prefix"]
    assert "plain_text_key" not in get_body
    assert "key_hash" not in get_body
    yield


@test_steps("test_get_requires_query_param")
def test_api_key_get_query_param_requires_key():
    email = f"api_key.get.missingparam.{uuid4().hex}@test.com"
    headers = TestUtils.register_and_login(email, "Passw0rd!123", "Missing Param")
    response = TestUtils.make_request("GET", "/app/api-key", headers=headers)
    assert response.status_code == 400
    yield


@test_steps("test_get_via_query_param")
def test_api_key_get_via_query_param_alias():
    headers = _register_login_and_create_workspace("api_key.query")
    # ensure subscription for the (single) workspace
    ws_resp = TestUtils.make_request("GET", "/app/workspace", headers=headers)
    assert ws_resp.status_code == 200
    workspace_key = ws_resp.json()[0]["workspace_key"]
    _ensure_active_subscription_for_workspace(workspace_key)
    response = TestUtils.make_request("POST", "/app/api-key", payload={}, headers=headers)
    assert response.status_code == 201
    api_key_key = response.json()["api_key_key"]

    response = TestUtils.make_request("GET", f"/app/api-key?api_key_key={api_key_key}", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body.get("api_key_key") == api_key_key
    assert "plain_text_key" not in body
    assert "key_hash" not in body
    yield


@test_steps("test_create_multiple_workspaces_rejected")
def test_api_key_create_multiple_workspaces_rejected():
    email = f"api_key.multiws.{uuid4().hex}@test.com"
    headers = TestUtils.register_and_login(email, "Passw0rd!123", "Multi WS")

    response = TestUtils.make_request("POST", "/app/workspace", payload={"name": "WS1"}, headers=headers)
    assert response.status_code == 201
    response = TestUtils.make_request("POST", "/app/workspace", payload={"name": "WS2"}, headers=headers)
    assert response.status_code == 201

    response = TestUtils.make_request("POST", "/app/api-key", payload={}, headers=headers)
    assert response.status_code == 400
    yield


@test_steps("test_non_member_get_returns_404", "test_non_member_delete_returns_404")
def test_api_key_non_member_access():
    owner_headers = _register_login_and_create_workspace("api_key.owner")
    ws_resp = TestUtils.make_request("GET", "/app/workspace", headers=owner_headers)
    assert ws_resp.status_code == 200
    _ensure_active_subscription_for_workspace(ws_resp.json()[0]["workspace_key"])
    response = TestUtils.make_request("POST", "/app/api-key", payload={}, headers=owner_headers)
    assert response.status_code == 201
    api_key_key = response.json()["api_key_key"]
    yield

    other_email = f"api_key.other.{uuid4().hex}@test.com"
    other_headers = TestUtils.register_and_login(other_email, "Passw0rd!123", "Other User")

    response = TestUtils.make_request("GET", f"/app/api-key/{api_key_key}", headers=other_headers)
    assert response.status_code == 404
    yield

    response = TestUtils.make_request("DELETE", f"/app/api-key/{api_key_key}", headers=other_headers)
    assert response.status_code == 404
    yield


@test_steps("test_revoke_sets_status", "test_revoke_idempotent")
def test_api_key_revoke_flow():
    headers = _register_login_and_create_workspace("api_key.revoke")
    ws_resp = TestUtils.make_request("GET", "/app/workspace", headers=headers)
    assert ws_resp.status_code == 200
    _ensure_active_subscription_for_workspace(ws_resp.json()[0]["workspace_key"])
    response = TestUtils.make_request("POST", "/app/api-key", payload={}, headers=headers)
    assert response.status_code == 201
    api_key_key = response.json()["api_key_key"]
    yield

    response = TestUtils.make_request("DELETE", f"/app/api-key/{api_key_key}", headers=headers)
    assert response.status_code == 204

    response = TestUtils.make_request("GET", f"/app/api-key/{api_key_key}", headers=headers)
    assert response.status_code == 200
    assert response.json().get("status") == "revoked"
    yield

    response = TestUtils.make_request("DELETE", f"/app/api-key/{api_key_key}", headers=headers)
    assert response.status_code == 204
    yield


@test_steps("test_invalid_uuid_get", "test_invalid_uuid_delete")
def test_api_key_invalid_uuid_rejected():
    headers = _register_login_and_create_workspace("api_key.invaliduuid")
    ws_resp = TestUtils.make_request("GET", "/app/workspace", headers=headers)
    assert ws_resp.status_code == 200
    _ensure_active_subscription_for_workspace(ws_resp.json()[0]["workspace_key"])

    response = TestUtils.make_request("GET", "/app/api-key/not-a-uuid", headers=headers)
    assert response.status_code == 400
    yield

    response = TestUtils.make_request("DELETE", "/app/api-key/not-a-uuid", headers=headers)
    assert response.status_code == 400
    yield

