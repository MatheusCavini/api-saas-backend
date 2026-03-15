"""Tests for /health endpoint."""
from pytest_steps import test_steps
import time
from test.utils import TestUtils


@test_steps("test_health_ok")
def test_health_returns_ok():
    """GET /health returns 200 and status ok without authentication."""
    response = TestUtils.make_request("GET", "/health")
    assert response.status_code == 200
    assert response.json().get("status") == "ok"
    yield


# def test_rate_limiter(auth_headers):
#     total_requests = 0
#     last_status = 0
#     last_body = ""
#     for _ in range(115):
#         response = TestUtils.make_request("GET", "/api/v1/sample_entities", headers=auth_headers)
#         last_status = response.status_code
#         last_body = response.text
#         total_requests += 1
        
#         if last_status == 429:
#             break  
#     assert last_status == 429, (
#         f"Rate limiter falhou após {total_requests} requests. "
#         f"Último status: {last_status}. Body: {last_body}"
#     )
#     assert 99 < total_requests < 110

