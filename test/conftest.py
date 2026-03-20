"""Pytest configuration and fixtures for black-box E2E tests."""
import os

import pytest

# Default token used by the running API (override via env in Docker/test runner)
os.environ.setdefault("AUTH_BEARER_TOKEN", "dev-token")


@pytest.fixture
def auth_headers():
    """Default Bearer token for tests."""
    return {"Authorization": "Bearer " + os.environ.get("AUTH_BEARER_TOKEN", "dev-token")}
    
@pytest.fixture
def admin_headers():
    return {"X-Admin-Token": os.environ.get("ADMIN_SECRET_KEY", "sample-admin-key") }
