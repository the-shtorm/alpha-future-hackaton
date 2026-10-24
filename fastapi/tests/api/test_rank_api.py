import copy
import json

import jsonschema
import pytest
from conftest import ROOT
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

URL = "/api/v1/recommendations/rank"


def test_http_happy_path_schema_and_model_info(client, headers, payload):
    assert client.get("/health/live").json() == {"status": "ok"}
    response = client.post(URL, json=payload, headers=headers)
    assert response.status_code == 200, response.text
    jsonschema.validate(
        response.json(), json.loads((ROOT / "contracts/rank-response.schema.json").read_text())
    )
    assert client.get("/health/ready").json() == {"status": "ready"}
    info = client.get("/api/v1/model-info", headers=headers).json()
    assert info["dimension"] == 384 and "Path" not in str(info)
    assert info["selectionPolicy"] == "top_k_cosine_distance_v1"
    assert info["maxCosineDistance"] is None
    assert len(response.json()["results"]) == len(payload["candidates"])
    assert not any(p["isRecommended"] for p in response.json()["results"])
    assert response.json()["metadata"]["warnings"] == ["RECOMMENDATION_THRESHOLD_NOT_CONFIGURED"]


@pytest.mark.parametrize(
    "header,code", [({}, "AUTH_REQUIRED"), ({"X-Internal-API-Key": "bad"}, "AUTH_INVALID")]
)
def test_auth(client, payload, header, code):
    response = client.post(URL, json=payload, headers=header)
    assert response.status_code == 401 and response.json()["error"]["code"] == code
    assert client.get("/api/v1/model-info", headers=header).status_code == 401


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_security",
        "boolean_security",
        "extra",
        "enum",
        "ineligible",
        "blank_id",
        "topk_bool",
        "duplicates_conditions",
    ],
)
def test_validation_is_private(client, payload, headers, mutation):
    sentinel = "PRIVATE_INPUT_ABC"
    payload["profile"]["request"]["description"] = sentinel
    if mutation == "missing_security":
        del payload["profile"]["security"]
    elif mutation == "boolean_security":
        payload["profile"]["security"]["collateralReady"] = True
    elif mutation == "extra":
        payload[sentinel] = sentinel
    elif mutation == "enum":
        payload["profile"]["request"]["purpose"] = sentinel
    elif mutation == "ineligible":
        payload["candidates"][0]["eligibilityStatus"] = "INELIGIBLE"
    elif mutation == "blank_id":
        payload["candidates"][0]["product"]["id"] = "   "
    elif mutation == "topk_bool":
        payload["topK"] = True
    else:
        payload["candidates"][0]["pendingConditions"] = [{"code": "a", "message": "b"}] * 2
    response = client.post(URL, json=payload, headers=headers)
    assert response.status_code == 422
    assert sentinel not in response.text and "input" not in response.text


def test_duplicate_id_not_ready_empty_and_inference_failure(client, application, payload, headers, encoder):
    payload["candidates"].append(copy.deepcopy(payload["candidates"][0]))
    response = client.post(URL, json=payload, headers=headers)
    assert response.json()["error"]["code"] == "DUPLICATE_PRODUCT_ID"
    application.state.ready = False
    assert client.get("/health/ready").status_code == 503
    assert client.post(URL, json=payload, headers=headers).json()["error"]["code"] == "MODEL_NOT_READY"
    application.state.ready = True
    payload["candidates"] = []
    assert client.post(URL, json=payload, headers=headers).json()["results"] == []
    assert not encoder.calls
    from conftest import FakeEncoder

    encoder.encode = lambda _: (_ for _ in ()).throw(RuntimeError("PRIVATE secret/path"))
    payload["candidates"] = json.loads((ROOT / "examples/rank-request.json").read_text())["candidates"]
    response = client.post(URL, json=payload, headers=headers)
    assert response.status_code == 500 and "PRIVATE" not in response.text
    encoder.encode = FakeEncoder().encode


def test_body_limit_without_content_length(settings, encoder):
    settings.max_request_bytes = 64
    app = create_app(settings, lambda _: encoder)
    with TestClient(app) as client:
        response = client.post(URL, content=iter([b"a" * 40, b"b" * 40]))
        assert response.status_code == 413
        assert client.post(URL, content=b"a" * 65).status_code == 413
        assert client.post(URL, content=b"{}", headers={"content-length": "invalid"}).status_code == 401


def test_startup_failure_and_shutdown(settings, encoder):
    app = create_app(settings, lambda _: (_ for _ in ()).throw(ValueError("private/path")))
    with pytest.raises(RuntimeError, match="initialization failed") as error:
        with TestClient(app):
            pass
    assert "private/path" not in str(error.value)
    app = create_app(settings, lambda _: encoder)
    with TestClient(app):
        assert app.state.ready
    assert not app.state.ready and app.state.runner.closed


@pytest.mark.parametrize("key", ["", "REPLACE_WITH_RANDOM_SECRET", "example" * 8])
def test_production_requires_real_secret(key):
    with pytest.raises(ValueError):
        Settings(ml_internal_api_key=key)


def test_wrong_model_disallowed():
    with pytest.raises(ValueError):
        Settings(environment="test", ml_internal_api_key="test", model_id="other")


def test_invalid_config_startup_is_sanitized(monkeypatch):
    monkeypatch.setenv("ML_INTERNAL_API_KEY", "")
    with pytest.raises(RuntimeError, match="Invalid service configuration"), TestClient(create_app()):
        pass


def test_unhandled_error_envelope(client, application):
    @application.get("/unexpected-test-only")
    def explode():
        raise RuntimeError("PRIVATE_EXCEPTION")

    response = client.get("/unexpected-test-only")
    assert response.status_code == 500 and "PRIVATE" not in response.text


def test_health_remains_responsive_and_busy_has_retry_after(settings, encoder, payload, headers):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    started, release = threading.Event(), threading.Event()
    original = encoder.encode
    settings.max_inflight_rank_requests = 1

    def slow(texts):
        started.set()
        assert release.wait(5)
        return original(texts)

    encoder.encode = slow
    with (
        TestClient(create_app(settings, lambda _: encoder)) as client,
        ThreadPoolExecutor(max_workers=1) as pool,
    ):
        first = pool.submit(client.post, URL, json=payload, headers=headers)
        assert started.wait(2)
        try:
            assert client.get("/health/live").status_code == 200
            assert client.get("/health/ready").status_code == 200
            response = client.post(URL, json=payload, headers=headers)
            assert response.status_code == 503 and response.headers["Retry-After"] == "1"
        finally:
            release.set()
        assert first.result().status_code == 200


@pytest.mark.parametrize("distance", [-0.01, 2.01, float("nan"), float("inf")])
def test_invalid_selection_distance_fails_configuration(distance):
    with pytest.raises(ValueError):
        Settings(environment="test", ml_internal_api_key="test", recommendation_max_cosine_distance=distance)


def test_configured_distance_reaches_ranker_and_model_info(settings, encoder, payload, headers):
    settings.recommendation_max_cosine_distance = 0
    with TestClient(create_app(settings, lambda _: encoder)) as client:
        response = client.post(URL, json=payload, headers=headers).json()
        assert len(response["results"]) == len(payload["candidates"])
        assert sum(p["isRecommended"] for p in response["results"]) == min(3, len(payload["candidates"]))
        assert response["metadata"]["maxCosineDistance"] == 0 and not response["metadata"]["warnings"]
        assert client.get("/api/v1/model-info", headers=headers).json()["maxCosineDistance"] == 0


def test_empty_distance_environment_is_unconfigured(monkeypatch):
    from app.core.config import calibrated_distance

    monkeypatch.setenv("RECOMMENDATION_MAX_COSINE_DISTANCE", "")
    assert (
        Settings(
            model_variant="base", environment="test", ml_internal_api_key="test"
        ).recommendation_max_cosine_distance
        == calibrated_distance()
    )
