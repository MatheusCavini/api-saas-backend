"""Pytest configuration and fixtures for black-box E2E tests."""
import sys
import os

import pytest

# Ensure `src/` is importable (e.g. `from models...`)
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SRC_DIR = os.path.join(_REPO_ROOT, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

# Default token used by the running API (override via env in Docker/test runner)
os.environ.setdefault("AUTH_BEARER_TOKEN", "dev-token")

# Default DB URL for importing SQLAlchemy models in tests.
# Tests can override with TEST_DATABASE_URL or DATABASE_URL.
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/api_db")


@pytest.fixture
def auth_headers():
    """Default Bearer token for tests."""
    return {"Authorization": "Bearer " + os.environ.get("AUTH_BEARER_TOKEN", "dev-token")}
    
@pytest.fixture
def admin_headers():
    return {"X-Admin-Token": os.environ.get("ADMIN_SECRET_KEY", "sample-admin-key") }
