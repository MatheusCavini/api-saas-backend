"""Utility helpers for black-box E2E tests."""
import os
from typing import Any, Optional
import jwt

import requests


class TestUtils:
    @staticmethod
    def make_request(method: str, endpoint: str, payload: Optional[dict] = None, headers: Optional[dict] = None, **kwargs: Any):
        """Make a real HTTP request to the running API and return the raw response."""
        base_url = os.environ.get("TEST_API_URL", "http://localhost:8000").rstrip("/")
        path = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        url = f"{base_url}{path}"
        request_headers = headers.copy() if headers else {}

        if payload is None:
            return requests.request(method, url, headers=request_headers, **kwargs)

        return requests.request(method, url, json=payload, headers=request_headers, **kwargs)

    def decode_token(token: str) -> dict:
        return jwt.decode(
            token,
            os.environ.get("JWT_SECRET", "test-secret"),
            algorithms=[os.environ.get("JWT_ALGORITHM", "HS256")],
        )