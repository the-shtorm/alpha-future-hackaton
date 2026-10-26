"""Opt-in real native package/API checks; prepare HF cache or supply a local package."""

import json
import os
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.routes.scoring import load_scoring
from app.core.config import ROOT
from app.main import create_app
from app.scoring.package import ScoringPackage
from scoring_training.tests.test_scoring_model import request_payload

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_SCORING_INTEGRATION") != "1", reason="Explicit real-package check"),
]
AUTH = {"Authorization": "Bearer test-key"}


def test_primary_package_identity_probability_and_score(settings, encoder):
    direct = load_scoring(settings).evaluate(request_payload())
    settings.scoring_enabled = True
    # Ranking encoder is a test double; scoring loads the actual pinned native model.
    with TestClient(create_app(settings, lambda _: encoder)) as client:
        assert client.get("/api/v1/scoring/ready", headers=AUTH).status_code == 200
        info = client.get("/api/v1/scoring/model-info", headers=AUTH).json()
        assert info["modelVersion"] == "sba-scoring-v2"
        assert info["calibrationVersion"] == "sba-scoring-v2-sigmoid-fy2012"
        assert info["operatingThreshold"] == 0.167204479067272
        response = client.post(
            "/api/v1/scoring/evaluate", json=request_payload().model_dump(mode="json"), headers=AUTH
        )
        assert response.status_code == 200
        result = response.json()
        assert result["modelVersion"] == "sba-scoring-v2"
        assert result["schemaVersion"] == "sba-scoring-1"
        assert result["featureVersion"] == "sba-features-1"
        assert result["sbaDefaultProbability"] == direct.sbaDefaultProbability
        probability = Decimal(str(result["sbaDefaultProbability"]))
        assert result["score"] == int(((1 - probability) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        assert result["isDemo"] is True
        assert {"SBA_US_TO_RU_DEMO", "TERM_HISTORY_UNCONFIRMED"} <= set(result["warnings"])


def test_wrong_version_does_not_fallback(settings, encoder, tmp_path):
    (tmp_path / "manifest.json").write_text('{"modelVersion":"wrong-version"}')
    settings.scoring_model_path = tmp_path
    settings.scoring_enabled = True
    with TestClient(create_app(settings, lambda _: encoder)) as client:
        assert client.get("/api/v1/scoring/ready", headers=AUTH).status_code == 503
        assert client.get("/health/ready").status_code == 200


def test_original_package_still_loads_with_rollback_pin():
    location = os.getenv("SCORING_V1_MODEL_PATH")
    if not location:
        pytest.skip("Legacy v1 is no longer bundled; supply SCORING_V1_MODEL_PATH to verify rollback")
    pin = json.loads((ROOT / "config/scoring-model-v1.lock.json").read_text())
    scorer = ScoringPackage(Path(location), pin["manifestSha256"])
    assert scorer.evaluate(request_payload()).modelVersion == "sba-scoring-v1"
    assert scorer.calibration.years == [2017, 2017]
