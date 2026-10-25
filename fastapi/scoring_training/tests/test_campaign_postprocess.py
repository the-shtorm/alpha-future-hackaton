"""Composition thresholds stay independent of validation labels and row order."""

import json

import numpy as np
import pytest
from scoring_training import campaign_fit, campaign_postprocess
from scoring_training.campaign_postprocess import blend_candidates, save_composition, write_csv
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


def test_end_to_end_postprocessing_keeps_metrics_and_artifacts_distinct(tmp_path, monkeypatch):
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
    monkeypatch.setattr(campaign_postprocess, "future_diagnostics", lambda *args: {})
    monkeypatch.setattr(campaign_postprocess, "plot_results", lambda *args: None)
    campaign_postprocess.postprocess(root, export, parents, parents)
    summary = json.loads((export / "summary.json").read_text())
    assert summary["recordCount"] == 11  # 2 base fits +4 calibrations +5 B-only blends.
    assert summary["distinctBaseModelArtifacts"] == 2
    assert summary["metricsAreAveraged"] is False
    assert summary["favoriteRetained"] is True
    leaders = json.loads((export / "leaders.json").read_text())
    assert leaders["bestWithoutTerm"]["config"]["bundle"] == "safe8_without_term"
    assert b"\r" not in (export / "trials.csv").read_bytes()
