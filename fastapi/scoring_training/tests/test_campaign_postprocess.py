"""Composition thresholds stay independent of validation labels and row order."""

import json

import numpy as np
import pytest
from scoring_training import campaign_fit, campaign_postprocess
from scoring_training.campaign_postprocess import blend_candidates, export_tables, save_composition, write_csv
from scoring_training.tests.test_campaign_data import sample
from scoring_training.train import write_json
from sklearn.metrics import f1_score, precision_score, recall_score


def config(name):
    return {"id": name, "stage": "calibration", "family": "catboost", "fold": "B", "seed": 42,
            "bundle": "safe8_without_term", "window": 5, "halfLife": None, "balance": 1}


def test_composition_selection_cannot_adapt_to_reversed_validation_labels(tmp_path):
    labels = np.array([1, 0, 1, 0, 1, 0])
    probability = np.array([0.9, 0.8, 0.7, 0.6, 0.5, 0.1])
    results = []
    for name, validation_labels in (("a", labels), ("b", 1 - labels)):
        results.append(save_composition(tmp_path, config(name), labels, probability, validation_labels,
                                        probability, {"kind": "test"}))
    assert results[0]["selectionSha256"] == results[1]["selectionSha256"]
    assert results[0]["selectionPoint"] == results[1]["selectionPoint"]
    policy = results[0]["primaryPolicy"]
    for result, actual_labels in zip(results, (labels, 1 - labels), strict=True):
        row = result["validation"][policy]
        predicted = probability >= row["threshold"]
        assert row["precision"] == precision_score(actual_labels, predicted)
        assert row["f1"] == f1_score(actual_labels, predicted)
        assert row["recall"] == recall_score(actual_labels, predicted)
        assert json.loads((tmp_path / "trials" / result["id"] / "selection.json").read_text()) == result["selection"]


def test_ensemble_rejects_misaligned_component_rows(tmp_path):
    parents = []
    for name, indices in (("a", [0, 1]), ("b", [1, 0])):
        path = tmp_path / f"{name}.npz"
        np.savez_compressed(path, thresholdIndices=indices, validationIndices=[2, 3],
                            thresholdLabels=[0, 1], validationLabels=[0, 1],
                            thresholdProbability=[0.1, 0.9], validationProbability=[0.1, 0.9])
        parents.append({"id": name, "config": config(name), "predictions": path.name, "artifact": "unused",
                        "signature": name})
    with pytest.raises(ValueError, match="alignment"):
        blend_candidates(tmp_path, parents, [])


def test_export_csv_has_portable_lf_bytes(tmp_path):
    path = tmp_path / "metrics.csv"
    write_csv(path, [{"precision": 0.6, "f1": 0.72, "recall": 0.9}])
    assert b"\r" not in path.read_bytes()


def test_failed_only_stage_exports_explicit_failure_without_fabricated_metrics(tmp_path):
    export_tables(tmp_path, [{"id": "failed", "config": config("failed"), "status": "failed",
                             "error": "test fixture failure"}])
    assert "test fixture failure" in (tmp_path / "trials.csv").read_text()
    assert "precision,f1,recall" in (tmp_path / "operating-points.csv").read_text()
    assert len((tmp_path / "operating-points.csv").read_text().splitlines()) == 1


@pytest.mark.parametrize("enable_mixed", [False, True])
@pytest.mark.parametrize("enable_recent", [False, True])
def test_end_to_end_postprocessing_keeps_metrics_and_artifacts_distinct(
    tmp_path, monkeypatch, enable_mixed, enable_recent
):
    root, export = tmp_path / "run", tmp_path / "export"
    root.mkdir()
    (root / "stages").mkdir()
    export.mkdir()
    write_json(export / "protocol.json", {"testFixture": True})
    write_json(export / "favorite-validation.json", {"byFold": {"B": {"metrics": {
        "precision": 0.4, "f1": 0.4, "recall": 0.4
    }}}})
    monkeypatch.setattr(campaign_fit, "_FRAME", sample())
    monkeypatch.setattr(campaign_fit, "_ROOT", root)
    parents = []
    for name, bundle in (("original", "original9_diagnostic_term_unconfirmed"), ("safe", "safe8_without_term")):
        parent = campaign_fit.run_trial({**config(name), "stage": "screening", "bundle": bundle,
                                         "parameters": {"iterations": 5}})
        assert parent["status"] == "complete", parent
        parents.append(parent)
    if enable_mixed:
        from scoring_training import campaign_mixed

        write_json(root / "mixed-policy.json", {"enabled": True})
        extra = {**parents[1], "id": "mixed-fixture", "config": {
            **parents[1]["config"], "id": "mixed-fixture", "stage": "mixed",
            "splitStrategy": "random_rows", "splitSeed": 42
        }}
        monkeypatch.setattr(campaign_mixed, "run_mixed_stage", lambda *args: [extra])
    if enable_recent:
        from scoring_training import campaign_recent_holdout

        write_json(root / "recent-holdout-policy.json", {"enabled": True})
        recent_extra = {**parents[1], "id": "recent-fixture", "config": {
            **parents[1]["config"], "id": "recent-fixture", "stage": "recent_holdout",
            "splitStrategy": "random_years", "splitSeed": 42
        }}
        monkeypatch.setattr(campaign_recent_holdout, "run_recent_stage", lambda *args: [recent_extra])
    monkeypatch.setattr(campaign_postprocess, "future_diagnostics", lambda *args: {})
    monkeypatch.setattr(campaign_postprocess, "plot_results", lambda *args: None)
    campaign_postprocess.postprocess(root, export, parents, parents)
    summary = json.loads((export / "summary.json").read_text())
    assert summary["recordCount"] == 11 + int(enable_mixed) + int(enable_recent)
    assert summary["mixedSplitRecords"] == int(enable_mixed)
    assert summary["recentHoldoutRecords"] == int(enable_recent)
    assert summary["distinctBaseModelArtifacts"] == 2
    assert summary["metricsAreAveraged"] is False
    assert summary["favoriteRetained"] is True
    assert "then recall, F1" in summary["ranking"]
    leaders = json.loads((export / "leaders.json").read_text())
    assert "top20ByRecallPriority" in leaders
    assert "then recall, F1" in json.loads((export / "top10.json").read_text())["ranking"]
    assert leaders["bestWithoutTerm"]["config"]["bundle"] == "safe8_without_term"
    assert b"\r" not in (export / "trials.csv").read_bytes()
