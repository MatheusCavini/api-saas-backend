"""Black-box E2E tests for user me resource."""
from __future__ import annotations

from pytest_steps import test_steps
from sqlalchemy import null

from test.utils import TestUtils


@test_steps("test_forbidden_no_token", "test_forbidden_wrong_token")
def test_forbidden_admin_endpoint():
    response = TestUtils.make_request("GET", "/admin/plan")
    assert response.status_code == 403
    yield

    response = TestUtils.make_request(
        "GET",
        "/admin/plan",
        headers={"X-Admin-Token": "wrong-token"},
    )
    assert response.status_code == 403
    yield


@test_steps("test_invalid_payload","test_create_plan_1", "test_create_plan_2", "test_get_plans")
def test_plan_create_and_list(admin_headers):
 
    response = TestUtils.make_request("POST", "/admin/plan", payload={"wrong": "data"}, headers=admin_headers)
    assert response.status_code == 400
    yield

    payload = {
        "name": "Test Plan 1",
        "monthly_quota": 100,
        "stripe_price_id": 'abc123'
    }
    response = TestUtils.make_request("POST", "/admin/plan", payload=payload, headers=admin_headers)
    assert response.status_code == 201
    body = response.json()
    assert body.get("name") == "Test Plan 1"
    assert body.get("plan_key")
    plan_key1 = body["plan_key"]
    yield

    payload = {
        "name": "Pro Plan 2",
        "monthly_quota": 10000,
        "stripe_price_id": 'def456'
    }
    response = TestUtils.make_request("POST", "/admin/plan", payload=payload, headers=admin_headers)
    assert response.status_code == 201
    body = response.json()
    assert body.get("name") == "Pro Plan 2"
    assert body.get("plan_key")
    plan_key2 = body["plan_key"]
    yield

    response = TestUtils.make_request("GET", "/admin/plan", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert any(item.get("plan_key") == plan_key1 for item in data)
    assert any(item.get("plan_key") == plan_key2 for item in data)
    yield


@test_steps("test_create_plan", "test_delete_plan", "assert_plan_not_listed")
def test_plan_delete(admin_headers):
    payload = {
        "name": "Enterprise",
        "monthly_quota": 10000,
        "stripe_price_id": 'ghi789'
    }
    response = TestUtils.make_request("POST", "/admin/plan", payload=payload, headers=admin_headers)
    assert response.status_code == 201
    body = response.json()
    assert body.get("name") == "Enterprise"
    assert body.get("plan_key")
    assert body.get("is_active") == True
    plan_key = body["plan_key"]
    yield

    payload = {
        "plan_key": plan_key
    }
    response = TestUtils.make_request("DELETE", "/admin/plan", payload=payload, headers=admin_headers)
    assert response.status_code == 204
    yield

    response = TestUtils.make_request("GET", "/admin/plan", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert not any(item.get("plan_key") == plan_key for item in data)
    yield


@test_steps("test_create_plan", "test_update_plan", "assert_updated")
def test_plan_update(admin_headers):
    payload = {
        "name": "Old Name",
        "monthly_quota": 10000,
        "stripe_price_id": 'jkl012'
    }
    response = TestUtils.make_request("POST", "/admin/plan", payload=payload, headers=admin_headers)
    assert response.status_code == 201
    body = response.json()
    assert body.get("name") == "Old Name"
    assert body.get("plan_key")
    assert body.get("is_active") == True
    plan_key = body["plan_key"]
    yield

    payload = {
        "plan_key": plan_key,
        "name": "New Name",
        "monthly_quota": 2000
    }
    response = TestUtils.make_request("PUT", "/admin/plan", payload=payload, headers=admin_headers)
    assert response.status_code == 200
    yield

    response = TestUtils.make_request("GET", "/admin/plan", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    updated_plan = None
    for plan in data:
        if plan.get("plan_key") == plan_key:
            updated_plan = plan
            break

    assert updated_plan.get("name") == "New Name"
    assert updated_plan.get("monthly_quota") == 2000
    yield
    