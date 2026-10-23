import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def test_health_is_available_without_database_credentials(client, monkeypatch):
    for variable in ("DB_URL", "DB_APP_PASSWORD", "DB_MIGRATOR_PASSWORD"):
        monkeypatch.delenv(variable, raising=False)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"status": "ok"}


def test_openapi_describes_the_health_response(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    operation = schema["paths"]["/health"]["get"]
    assert operation["tags"] == ["health"]
    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert response_schema["type"] == "object"
    assert response_schema["additionalProperties"]["type"] == "string"


def test_swagger_ui_loads_the_service_schema(client):
    response = client.get("/docs")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "SwaggerUIBundle" in response.text
    assert "/openapi.json" in response.text


def test_unknown_route_is_not_reported_as_healthy(client):
    assert client.get("/missing").status_code == 404


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_health_rejects_mutating_requests(client, method):
    assert client.request(method, "/health").status_code == 405
