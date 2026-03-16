# """Black-box E2E tests for sample_entity resource."""
# from pytest_steps import test_steps

# from test.utils import TestUtils


# @test_steps("test_create_invalid", "test_create_valid")
# def test_create_entity(auth_headers):
#     """Validate request schema and happy path create."""
#     payload = {"wrong": "data"}
#     response = TestUtils.make_request("POST", "/api/v1/sample_entities", payload=payload, headers=auth_headers)
#     assert response.status_code == 400
#     yield

#     payload = {"name": "Test", "email": "randomt@test.com"}
#     response = TestUtils.make_request("POST", "/api/v1/sample_entities", payload=payload, headers=auth_headers)
#     assert response.status_code == 201
#     body = response.json()
#     assert body.get("name") == "Test"
#     assert "id" in body
#     yield


# @test_steps("test_list_entities", "test_get_not_found")
# def test_list_and_get(auth_headers):
#     """List returns array; requesting non-existent id returns 404."""
#     response = TestUtils.make_request("GET", "/api/v1/sample_entities", headers=auth_headers)
#     assert response.status_code == 200
#     assert isinstance(response.json(), list)
#     yield

#     response = TestUtils.make_request("GET", "/api/v1/sample_entities/999999", headers=auth_headers)
#     assert response.status_code == 404
#     yield


# @test_steps("test_crud_create", "test_crud_get", "test_crud_update", "test_crud_delete")
# def test_crud_flow(auth_headers):
#     """Create -> Get -> Update -> Delete against the live API."""
#     payload = {"name": "Flow", "email": "flow@test.com"}
#     response = TestUtils.make_request("POST", "/api/v1/sample_entities", payload=payload, headers=auth_headers)
#     assert response.status_code == 201
#     entity_id = response.json().get("id")
#     assert entity_id is not None
#     yield

#     response = TestUtils.make_request("GET", f"/api/v1/sample_entities/{entity_id}", headers=auth_headers)
#     assert response.status_code == 200
#     assert response.json().get("name") == "Flow"
#     yield

#     payload = {"name": "Flow Updated"}
#     response = TestUtils.make_request("PUT", f"/api/v1/sample_entities/{entity_id}", payload=payload, headers=auth_headers)
#     assert response.status_code == 200
#     assert response.json().get("name") == "Flow Updated"
#     yield

#     response = TestUtils.make_request("DELETE", f"/api/v1/sample_entities/{entity_id}", headers=auth_headers)
#     assert response.status_code == 204
#     yield


# @test_steps("test_unauthorized_no_token", "test_unauthorized_bad_token")
# def test_unauthorized_requests():
#     """Requests without a valid Bearer token should be rejected."""
#     response = TestUtils.make_request("GET", "/api/v1/sample_entities")
#     assert response.status_code == 401
#     yield

#     response = TestUtils.make_request(
#         "GET",
#         "/api/v1/sample_entities",
#         headers={"Authorization": "Bearer wrong-token"},
#     )
#     assert response.status_code == 401
#     yield


# @test_steps("test_options_cors")
# def test_options_cors():
#     """OPTIONS request returns 200 and is handled by CORS."""
#     response = TestUtils.make_request("OPTIONS", "/api/v1/sample_entities")
#     assert response.status_code == 200
#     assert response.headers.get("Access-Control-Allow-Origin") == "*"
#     yield

