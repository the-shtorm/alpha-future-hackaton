import json

import pytest

from app.core import config
from app.core.config import Settings
from scripts.calibrate import choose_threshold, digest, load_data, metrics


def test_threshold_is_chosen_only_from_supplied_calibration_scores():
    rows = [
        {
            "id": "cal",
            "relevant": ["good"],
            "ranking": [{"code": "good", "score": 0.9}, {"code": "bad", "score": 0.8}],
        }
    ]
    threshold, search = choose_threshold(rows)
    assert 0.1 <= threshold < 0.2
    result = metrics(rows, threshold)
    assert result["precision"] == result["recall"] == result["f1"] == 1
    assert search
    # No positives means abstention is preferred, not arbitrary recommendations.
    rows[0]["relevant"] = []
    assert choose_threshold(rows)[0] == 0


def test_selection_metrics_apply_top_three_and_measure_abstention():
    rows = [
        {
            "id": "one",
            "relevant": ["fourth"],
            "ranking": [{"code": str(i), "score": 0.9} for i in range(3)]
            + [{"code": "fourth", "score": 0.8}],
        },
        {"id": "none", "relevant": [], "ranking": [{"code": "x", "score": -0.1}]},
    ]
    result = metrics(rows, 0.2)
    assert result["fn"] == 1 and result["fp"] == 3
    assert result["abstentionCount"] == result["noRelevantAbstentionCount"] == 1
    assert result["recommendationCountHistogram"] == {"0": 1, "1": 0, "2": 0, "3": 1}


def test_new_datasets_are_disjoint_and_diverse():
    catalog, calibration, holdout = load_data()
    assert len(catalog) == 15
    assert len(calibration["scenarios"]) == 180 and len(holdout["scenarios"]) == 90
    rows = calibration["scenarios"] + holdout["scenarios"]
    assert len({s["intent"] for s in rows}) == 15
    assert len({s["profile"]["request"]["purpose"] for s in rows}) == 8
    assert {s["profile"]["request"]["usageMode"] for s in rows} == {
        "ONE_TIME",
        "IN_PARTS",
        "ACCOUNT_RESERVE",
        "UNKNOWN",
    }
    assert {s["profile"]["security"]["guarantorReady"] for s in rows} == {"YES", "NO", "DISCUSS", "UNKNOWN"}
    assert any(s["profile"]["request"].get("description") is None for s in rows)
    assert any(not s["relevantProductCodes"] for s in rows)
    assert all(s["labelStatus"] == "SYNTHETIC_PROPOSED" for s in rows)


def test_selection_policy_is_pinned_and_overridable():
    policy = json.loads((config.ROOT / "config/selection-policy.json").read_text(encoding="utf-8"))
    assert policy["calibrationSha256"] == digest(config.ROOT / "evaluation/calibration.json")
    assert policy["productsSha256"] == digest(config.ROOT / "evaluation/backend-products.json")
    assert (
        Settings(
            model_variant="base", environment="test", ml_internal_api_key="x"
        ).recommendation_max_cosine_distance
        == policy["maxCosineDistance"]
    )
    assert (
        Settings(
            environment="test", ml_internal_api_key="x", recommendation_max_cosine_distance=0
        ).recommendation_max_cosine_distance
        == 0
    )


def test_missing_and_incompatible_calibration_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ROOT", tmp_path)
    assert config.calibrated_distance() is None
    (tmp_path / "config").mkdir()
    (tmp_path / "config/model.lock.json").write_text(json.dumps({"revision": "a" * 40}))
    (tmp_path / "config/selection-policy.json").write_text(json.dumps({"policyVersion": "wrong"}))
    with pytest.raises(ValueError, match="does not match"):
        config.calibrated_distance()
