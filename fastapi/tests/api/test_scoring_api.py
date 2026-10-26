from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.scoring.contracts import ScoringResponse
from app.scoring.package import ScoringPackage, digest
from scoring_training.tests.test_scoring_model import package_fixture, request_payload  # noqa: F401

AUTH = {"Authorization": "Bearer test-key"}


class FixtureScorer:
    manifest = SimpleNamespace(
        modelVersion="fixture-only",
        featureVersion="sba-features-1",
        calibrationVersion="fixture-sigmoid",
        naicsMode="full",
    )

    def evaluate(self, request):
        return ScoringResponse(
            schemaVersion="sba-scoring-1",
            requestId=request.requestId,
            sbaDefaultProbability=0.155,
            score=85,
            modelVersion="fixture-only",
            featureVersion="sba-features-1",
            calibrationVersion="fixture-sigmoid",
            domainStatus="IN_RANGE",
            isDemo=True,
            warnings=["SBA_US_TO_RU_DEMO"],
        )


@pytest.fixture
def scoring_client(settings, encoder):
    settings.scoring_enabled = True
    with TestClient(
        create_app(settings, lambda _: encoder, lambda _: FixtureScorer()), raise_server_exceptions=False
    ) as client:
        yield client


def test_auth_readiness_and_independent_ranking(client, scoring_client):
    payload = request_payload().model_dump(mode="json")
    assert client.post("/api/v1/scoring/evaluate", json=payload, headers=AUTH).status_code == 503
    assert client.get("/health/ready").status_code == 200
    for headers in ({}, {"Authorization": "Bearer invalid"}):
        assert (
            scoring_client.post("/api/v1/scoring/evaluate", json=payload, headers=headers).status_code == 401
        )
    assert scoring_client.get("/api/v1/scoring/ready", headers=AUTH).status_code == 200
    assert scoring_client.get("/api/v1/scoring/model-info", headers=AUTH).json()["positiveClass"] == 1
    response = scoring_client.post("/api/v1/scoring/evaluate", json=payload, headers=AUTH)
    assert response.status_code == 200
    assert response.json()["requestId"] == payload["requestId"]
    assert response.json()["score"] == 85


@pytest.mark.parametrize(
    "field,value",
    [
        ("termMonths", True),
        ("termMonths", 12.0),
        ("isRevolving", "false"),
        ("businessType", "SECRET-UNKNOWN"),
        ("naicsCode", 445110),
        ("loanAmountUsd", "NaN"),
        ("extra-secret", "secret-value"),
    ],
)
def test_validation_is_strict_and_sanitized(scoring_client, field, value):
    payload = request_payload().model_dump(mode="json")
    payload[field] = value
    response = scoring_client.post("/api/v1/scoring/evaluate", json=payload, headers=AUTH)
    assert response.status_code == 422
    assert "sba-scoring-1" in response.json()["error"]["message"]
    assert "secret" not in response.text.lower()


def test_bad_package_keeps_scoring_unready_but_recsys_ready(settings, encoder):
    settings.scoring_enabled = True

    def broken(_):
        raise RuntimeError("internal-secret-path")

    with TestClient(create_app(settings, lambda _: encoder, broken)) as client:
        response = client.get("/api/v1/scoring/ready", headers=AUTH)
        assert response.status_code == 503
        assert "secret" not in response.text
        assert client.get("/health/ready").status_code == 200


def test_internal_inference_failure_does_not_leak(settings, encoder):
    settings.scoring_enabled = True

    class Broken(FixtureScorer):
        def evaluate(self, _):
            raise RuntimeError("internal-secret-path")

    with TestClient(
        create_app(settings, lambda _: encoder, lambda _: Broken()), raise_server_exceptions=False
    ) as client:
        payload = request_payload().model_dump(mode="json")
        response = client.post("/api/v1/scoring/evaluate", json=payload, headers=AUTH)
        assert response.status_code == 500
        assert response.json()["requestId"] == payload["requestId"]
        assert "secret" not in response.text


def test_http_with_real_serialized_model(settings, encoder, package_fixture):  # noqa: F811
    package, _, _, _ = package_fixture
    settings.scoring_enabled = True
    with TestClient(
        create_app(
            settings, lambda _: encoder, lambda _: ScoringPackage(package, digest(package / "manifest.json"))
        )
    ) as client:
        payload = request_payload().model_dump(mode="json")
        payload["initialInterestRatePct"] = "28.00"
        response = client.post("/api/v1/scoring/evaluate", json=payload, headers=AUTH)
        assert response.status_code == 200
        assert response.json()["domainStatus"] == "EXTRAPOLATION"
        assert "RATE_OUT_OF_RANGE" in response.json()["warnings"]


def test_scoring_body_limit_and_http_queue_saturation(settings, encoder):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    entered, finish = threading.Event(), threading.Event()

    class Blocking(FixtureScorer):
        def evaluate(self, request):
            entered.set()
            finish.wait(timeout=5)
            return super().evaluate(request)

    settings.scoring_enabled = True
    with TestClient(
        create_app(settings, lambda _: encoder, lambda _: Blocking()), raise_server_exceptions=False
    ) as client:
        payload = request_payload().model_dump(mode="json")
        assert client.post("/api/v1/scoring/evaluate", content=b"x" * 600000, headers=AUTH).status_code == 413
        with ThreadPoolExecutor(max_workers=4) as pool:
            waiting = [
                pool.submit(client.post, "/api/v1/scoring/evaluate", json=payload, headers=AUTH)
                for _ in range(4)
            ]
            assert entered.wait(timeout=1)
            try:
                # Wait for all four admitted requests, then exercise the HTTP 503 envelope.
                import time

                deadline = time.monotonic() + 1
                while (
                    client.get("/api/v1/scoring/model-info", headers=AUTH).json()["runtime"][
                        "inflightRequests"
                    ]
                    < 4
                ):
                    assert time.monotonic() < deadline
                    time.sleep(0.005)
                response = client.post("/api/v1/scoring/evaluate", json=payload, headers=AUTH)
                assert response.status_code == 503
                assert response.json()["error"]["code"] == "SERVICE_BUSY"
                assert response.headers["Retry-After"] == "1"
            finally:
                finish.set()
            assert all(request.result().status_code == 200 for request in waiting)
        status = client.get("/api/v1/scoring/model-info", headers=AUTH).json()["runtime"]
        assert status["inflightRequests"] == 0
        assert status["completedRequests"] == 4 and status["busyRequests"] == 1
