from __future__ import annotations
from uuid import uuid4
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from pytest_steps import test_steps
from test.utils import TestUtils

@test_steps(
    "setup_dependencies",
    "test_checkout_invalid_plan",
    "test_checkout_success",
)
def test_subscription(admin_headers):
    # --- STEP 1: SETUP DEPENDENCIES ---
    plan_payload = {
        "name": "E2E Stripe Plan",
        "monthly_quota": 5000,
        "stripe_price_id": "price_1TF1NO3S9rGghWRUv7Yz2gOM"
    }
    response = TestUtils.make_request("POST", "/admin/plan", payload=plan_payload, headers=admin_headers)
    assert response.status_code == 201
    plan_data = response.json()
    plan_key = plan_data["plan_key"]
    plan_id = plan_data.get("id", 1)

    owner_email = f"owner.{uuid4().hex}@test.com"
    owner_headers = TestUtils.register_and_login(owner_email, "Passw0rd!123", "owner")

    payload = {"name": "MyWorkspace"}
    response = TestUtils.make_request("POST", "/app/workspace", payload=payload, headers=owner_headers)
    assert response.status_code == 201
    yield

    # --- STEP 2: CHECKOUT WITH INVALID PLAN ---
    response = TestUtils.make_request(
        "POST", 
        "/app/stripe/select", 
        payload={"plan_key": str(uuid4())}, 
        headers=owner_headers
    )
    assert response.status_code == 404
    yield

    # --- STEP 3: SUCCESSFUL CHECKOUT ---
    response = TestUtils.make_request(
        "POST", 
        "/app/stripe/select", 
        payload={"plan_key": plan_key}, 
        headers=owner_headers
    )
    assert response.status_code == 200
    assert response.json().get("url") is not None
    yield

    
    