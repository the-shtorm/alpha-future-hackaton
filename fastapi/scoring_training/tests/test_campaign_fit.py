"""Actual tiny fitted trials verify freeze order, serialization and restart behavior."""

import importlib.util
import json

import joblib
import numpy as np
import pytest
from scoring_training import campaign_fit
from scoring_training.tests.test_campaign_data import sample


@pytest.mark.parametrize("family", ["catboost", "logistic", "randomForest", "lightgbm", "xgboost"])
def test_real_trial_freezes_selection_and_preserves_artifact_predictions(tmp_path, monkeypatch, family):
    if family in ("lightgbm", "xgboost") and importlib.util.find_spec(family) is None:
        pytest.skip("Optional campaign competitor is not installed")
    monkeypatch.setattr(campaign_fit, "_FRAME", sample())
    monkeypatch.setattr(campaign_fit, "_ROOT", tmp_path)
    config = {"id": family, "family": family, "bundle": "safe8_without_term", "fold": "B",
              "window": 5, "halfLife": 3, "balance": 3, "seed": 42,
              "parameters": {"catboost": {"iterations": 5}, "logistic": {"C": 1},
                             "randomForest": {"max_depth": 2}, "lightgbm": {"max_depth": 2},
                             "xgboost": {"max_depth": 2}}[family]}
    original = campaign_fit.evaluate_points

    def checked_evaluation(selection, labels, probability):
        frozen = json.loads((tmp_path / "trials" / family / "selection.json").read_text())
        assert frozen == selection
        return original(selection, labels, probability)

    monkeypatch.setattr(campaign_fit, "evaluate_points", checked_evaluation)
    result = campaign_fit.run_trial(config)
    assert result["status"] == "complete", result
    saved = joblib.load(tmp_path / result["artifact"])
    frame = campaign_fit._FRAME.query("ApprovalFY == 2023")
    raw = campaign_fit.raw_prediction(saved["model"], saved["builder"].transform(frame), family, saved["categories"])
    stored = np.load(tmp_path / result["predictions"])
    np.testing.assert_allclose(raw, stored["validationRaw"])
    assert campaign_fit.run_trial(config) == result
    for name, row in result["validation"].items():
        assert row["threshold"] == result["selection"][name]["threshold"]


def test_signature_deduplicates_identical_windows_without_merging_distinct_fits():
    base = {"id": "first", "stage": "screening", "family": "catboost", "fold": "B", "window": None}
    assert campaign_fit.signature(base) == campaign_fit.signature({**base, "id": "other", "window": 10})
    assert campaign_fit.signature(base) != campaign_fit.signature({**base, "window": 3})


def test_failed_fit_is_reported_and_never_ranked_as_a_success(tmp_path, monkeypatch):
    monkeypatch.setattr(campaign_fit, "_FRAME", sample())
    monkeypatch.setattr(campaign_fit, "_ROOT", tmp_path)
    result = campaign_fit.run_trial({"id": "bad", "family": "unknown", "bundle": "safe8_without_term",
                                    "fold": "B", "seed": 42})
    assert result["status"] == "failed"
    assert "Unknown candidate family" in result["error"]
    assert campaign_fit.result_rank(result) == (-1,)
