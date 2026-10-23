from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest

from app import healthcheck, server
from app.settings import get_port


@pytest.fixture(autouse=True)
def clean_port(monkeypatch):
    monkeypatch.delenv("PORT", raising=False)


def test_default_port(monkeypatch):
    monkeypatch.delenv("PORT", raising=False)
    assert get_port() == 8000


@pytest.mark.parametrize("port", ["1", "8080", "65535"])
def test_cloud_port(monkeypatch, port):
    monkeypatch.setenv("PORT", port)
    assert get_port() == int(port)


@pytest.mark.parametrize("port", ["", "http", "8000.5", "0", "-1", "65536"])
def test_invalid_port_fails_before_startup(monkeypatch, port):
    monkeypatch.setenv("PORT", port)
    with pytest.raises(ValueError, match="PORT must be an integer between 1 and 65535"):
        get_port()


def test_server_listens_on_the_cloud_port_and_all_interfaces(monkeypatch):
    monkeypatch.setenv("PORT", "8080")
    with patch("app.server.uvicorn.run") as run:
        server.main()
    run.assert_called_once_with("app.main:app", host="0.0.0.0", port=8080)


def test_healthcheck_uses_the_same_cloud_port_and_closes_response(monkeypatch):
    monkeypatch.setenv("PORT", "8080")
    response = MagicMock()
    response.__enter__.return_value.status = 200
    with patch("app.healthcheck.urlopen", return_value=response) as request:
        healthcheck.main()
    request.assert_called_once_with("http://127.0.0.1:8080/health", timeout=2)
    response.__exit__.assert_called_once()


def test_healthcheck_rejects_non_200_response():
    response = MagicMock()
    response.__enter__.return_value.status = 204
    with patch("app.healthcheck.urlopen", return_value=response):
        with pytest.raises(RuntimeError, match="HTTP 200"):
            healthcheck.main()


@pytest.mark.parametrize("error", [URLError("connection refused"), HTTPError("/health", 503, "unavailable", {}, None)])
def test_healthcheck_propagates_connection_and_http_failures(error):
    with patch("app.healthcheck.urlopen", side_effect=error):
        with pytest.raises(URLError):
            healthcheck.main()
