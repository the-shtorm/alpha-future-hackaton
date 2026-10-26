"""A fallback is a post-run result, never a target claim or unverified cleanup."""

import json

import joblib
import numpy as np
import pandas as pd
import pytest
from scoring_training import campaign_fallback as fallback
from scoring_training.data import sha256_file
from scoring_training.tests.test_campaign_retention import LABELS, candidate
from scoring_training.thresholds import threshold_table
from scoring_training.train import write_json


def test_substantial_selection_prioritizes_recall_rejects_regressions_and_deduplicates(tmp_path):
    labels = np.r_[np.ones(10, dtype=int), np.zeros(10, dtype=int)]
    rows = []
    for name, tp, fp in (("precision", 6, 0), ("recall", 8, 5), ("duplicate", 8, 5),
                         ("weak", 4, 0), ("regression", 9, 10)):
        probability = np.r_[np.full(tp, .9), np.full(10 - tp, .1),
                            np.full(fp, .9), np.full(10 - fp, .1)]
        path = tmp_path / f"{name}.npz"
        np.savez_compressed(path, validationIndices=np.arange(20), validationProbability=probability)
        point = threshold_table(labels, probability, [.5])[0]
        rows.append({"id": name, "status": "complete", "config": {"bundle": "safe8_without_term"},
                     "primaryPolicy": "optimal", "selectionPoint": point,
                     "validation": {"optimal": point}, "predictions": path.name})
    rows[2]["config"]["calibrationMethod"] = "none"
    chosen, count = fallback.select_substantial_improvements(
        tmp_path, rows, {"precision": .5, "recall": .4, "f1": 4 / 9})
    assert count == 3
    assert [r["id"] for r in chosen] == ["recall", "precision"]
    assert chosen[0]["selectionPoint"]["f1"] < chosen[1]["selectionPoint"]["f1"]


def program_fixture(tmp_path, monkeypatch):
    root, export = tmp_path / "run", tmp_path / "export"
    (root / "stages").mkdir(parents=True)
    (root / "stage-commits").mkdir()
    export.mkdir()
    rows = []
    for name, probability in (("a", [.9, .1, .9, .1, .1, .1]),
                              ("b", [.9, .1, .1, .1, .9, .1])):
        row = candidate(root, name, np.array(probability))
        row.update(status="complete", validationTargetPassed=False,
                   selection={"optimal": row["selectionPoint"]})
        row["config"].update(family="catboost", stage="screening", fold="B", seed=42)
        path = root / "trials" / name / "selection.json"
        write_json(path, row["selection"])
        row["selectionSha256"] = sha256_file(path)
        rows.append(row)
    for stage, count in fallback.REQUIRED_STAGES.items():
        write_json(root / "stages" / f"{stage}-results.json", [rows[0]] * count)
    write_json(root / "stages" / "postprocess-results.json", rows)
    write_json(root / "committer-status.json", {"status": "complete"})
    write_json(root / "stage-commits" / "postprocess.json", {"commit": "fixture"})
    summary = {"status": "complete_no_feasible", "top10Count": 0, "mixedSplitRecords": 72,
               "recentHoldoutRecords": 200, "failedRecords": [], "recordCount": 1394}
    write_json(root / "progress.json", {"stage": "complete", "summary": summary})
    write_json(export / "summary.json", summary)
    write_json(export / "top10.json", {"candidates": []})
    (export / "top10.csv").write_text("rank,id\n")
    (export / "README.md").write_text("# Campaign\nТоп-10 пуст; все веса сохранены, очистки не было.\n")
    write_json(root / "retention.json", {"allTrialWeightsPreserved": True, "deletedFiles": 0})
    write_json(export / "favorite-validation.json", {"byFold": {"B": {"metrics": {
        "precision": .4, "recall": .4, "f1": .4}}}})
    joblib.dump(pd.DataFrame({"sourceRowIndex": np.arange(6), "LoanStatus": LABELS,
                             "ApprovalFY": 2023, "approvalDate": pd.date_range("2023-01-01", periods=6)}),
                root / "dataset.joblib")
    monkeypatch.setattr(fallback, "protect_favorite", lambda *args: None)
    monkeypatch.setattr(fallback, "future_diagnostics", lambda *args: {})
    monkeypatch.setattr(fallback, "plot_results", lambda *args: None)
    monkeypatch.setattr(fallback, "artifact_probability", lambda base, artifact, frame:
                        joblib.load(base / artifact)["probability"])
    return root, export, rows


def test_final_fallback_replays_backs_up_target_exports_and_is_idempotent(tmp_path, monkeypatch):
    root, export, rows = program_fixture(tmp_path, monkeypatch)
    trash = candidate(root, "not_selected", np.array([.9, .9, .9, .9, .9, .9]))
    outcome = fallback.finalize_fallback(root, export)
    assert outcome["status"] == "complete" and outcome["top10Count"] == 2
    assert outcome["targetAchieved"] is False
    assert "не достигнуты" in (export / "fallback-report.md").read_text()
    assert "Резервные существенные улучшения" in (export / "README.md").read_text()
    assert "Топ-10 пуст" in (export / "target-only-README.md").read_text()
    assert json.loads((export / "target-only-top10.json").read_text())["candidates"] == []
    assert json.loads((export / "target-only-summary.json").read_text())["status"] == "complete_no_feasible"
    top = json.loads((export / "top10.json").read_text())
    assert top["selectionTier"] == "substantial_improvement_below_target"
    assert all(r["id"] in {"a", "b"} for r in top["candidates"])
    assert not (root / trash["artifact"]).exists()
    assert all((root / row["artifact"]).exists() for row in rows)
    retention = json.loads((export / "retention.json").read_text())
    assert retention["cleanupComplete"] and len(retention["verification"]) == 2
    assert all(r["validationReplayPassed"] for r in retention["verification"])
    write_json(export / "artifact-hashes.json", {})
    write_json(root / "progress.json", {"stage": "fixture interrupted checkpoint"})
    assert fallback.finalize_fallback(root, export) == outcome
    assert json.loads((export / "retention.json").read_text())["deletedFiles"] == retention["deletedFiles"]
    assert json.loads((root / "progress.json").read_text())["stage"] == "complete"
    hashes = json.loads((export / "artifact-hashes.json").read_text())
    assert hashes["top10.json"] == sha256_file(export / "top10.json")


@pytest.mark.parametrize("problem", ["stage", "committer", "target", "hidden_target"])
def test_partial_program_or_existing_target_winner_forbids_fallback(tmp_path, monkeypatch, problem):
    root, export, rows = program_fixture(tmp_path, monkeypatch)
    if problem == "stage":
        write_json(root / "stages" / "recent_holdout-results.json", [rows[0]] * 199)
    elif problem == "committer":
        write_json(root / "committer-status.json", {"status": "running"})
    elif problem == "target":
        write_json(export / "top10.json", {"candidates": [rows[0]]})
    else:
        rows[0]["validation"]["optimal"].update(precision=1., recall=1., f1=1.)
        write_json(root / "stages" / "postprocess-results.json", rows)
    with pytest.raises(ValueError):
        fallback.finalize_fallback(root, export)
    assert all((root / row["artifact"]).exists() for row in rows)
    assert not (root / "fallback-plan.json").exists()


def test_metadata_failure_after_replay_can_resume_without_losing_retention_history(tmp_path, monkeypatch):
    root, export, _ = program_fixture(tmp_path, monkeypatch)
    original_writer = fallback.write_json

    def fail_summary(path, value):
        if path == export / "summary.json" and value.get("fallbackSelection"):
            raise OSError("fixture metadata write failure")
        original_writer(path, value)

    monkeypatch.setattr(fallback, "write_json", fail_summary)
    with pytest.raises(OSError, match="fixture metadata"):
        fallback.finalize_fallback(root, export)
    ledger = json.loads((root / "retention.json").read_text())
    assert ledger["cleanupComplete"]
    monkeypatch.setattr(fallback, "write_json", original_writer)
    result = fallback.finalize_fallback(root, export)
    assert result["top10Count"] == 2
    assert json.loads((root / "retention.json").read_text()) == ledger


def test_no_substantial_improvement_keeps_all_weights_and_empty_target_list(tmp_path, monkeypatch):
    root, export, rows = program_fixture(tmp_path, monkeypatch)
    write_json(export / "favorite-validation.json", {"byFold": {"B": {"metrics": {
        "precision": 1., "recall": .8, "f1": .88}}}})
    result = fallback.finalize_fallback(root, export)
    assert result["status"] == "no_substantial_improvement"
    assert result["allTrialWeightsPreserved"]
    assert all((root / row["artifact"]).exists() for row in rows)
    assert json.loads((export / "top10.json").read_text())["candidates"] == []
