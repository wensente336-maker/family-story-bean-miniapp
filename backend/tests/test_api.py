from fastapi.testclient import TestClient

from app.main import app
from app.mock_data import JOB_ID


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_mock_home_contract() -> None:
    response = client.get("/v1/mock/home", headers={"X-Request-Id": "test-request"})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["meta"]["request_id"] == "test-request"
    assert body["data"]["family"]["name"] == "小满一家"
    assert body["data"]["processing"]["progress"] == 68
    assert len(body["data"]["moments"]) == 2


def test_web_home_requires_authentication() -> None:
    response = client.get("/v1/home", headers={"X-Request-Id": "web-contract-test"})
    assert response.status_code == 401
    assert response.headers["X-Request-Id"] == "web-contract-test"
    assert response.json()["meta"]["request_id"] == "web-contract-test"
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_web_cors_preflight_allows_configured_local_origin() -> None:
    response = client.options(
        "/v1/home",
        headers={
            "Origin": "http://127.0.0.1:4173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Request-Id",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:4173"
    assert "X-Request-Id" in response.headers["access-control-allow-headers"]


def test_mock_job_not_found_uses_standard_error() -> None:
    response = client.get("/v1/mock/jobs/not-a-job")
    assert response.status_code == 404
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "JOB_NOT_FOUND"


def test_mock_job_found() -> None:
    response = client.get(f"/v1/mock/jobs/{JOB_ID}")
    assert response.status_code == 200
    assert response.json()["data"]["stage"] == "ANALYZING"
