"""Historical shuffled roles and later-year evaluation remain separate."""

import copy
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from scoring_training import campaign, campaign_fit
from scoring_training import campaign_recent_holdout as recent
from scoring_training.campaign_postprocess import artifact_probability
from scoring_training.data import sha256_file
from scoring_training.tests.test_campaign_data import sample
from scoring_training.thresholds import threshold_table
from scoring_training.train import write_json


def source_frame():
    example = sample().iloc[0].to_dict()
    rows = []
    for year in range(2010, 2027):
        for label in (0, 1):
            count = 5 if year == 2019 and label else 120
            if year == 2026 and label:
                count = 0
            for i in range(count):
                rows.append({**example, "ApprovalFY": year, "LoanStatus": label,
                             "approvalDate": pd.Timestamp(year, 1, 1),
                             "outcomeDate": pd.Timestamp(year, 3, 1),
                             "GrossApproval": 10000 + i * 20 + label * 100,
                             "sourceRowIndex": len(rows)})
    return pd.DataFrame(rows)


def parent(index=0):
    return {"id": f"parent-{index}", "status": "complete", "primaryPolicy": "optimal",
            "config": {"family": "catboost", "bundle": "safe8_without_term", "stage": "refinement",
                       "fold": "B", "seed": 42, "parameters": {"l2_leaf_reg": index + 1}},
            "validation": {"optimal": {"precision": .6, "recall": .95, "f1": .735}}}


def tiny_config(tmp_path, strategy):
    (tmp_path / "stages").mkdir(exist_ok=True)
    config = next(c for c in recent.frozen_configurations(tmp_path, [parent()], 1)
                  if c["splitStrategy"] == strategy)
    config.update(parameters={"iterations": 5}, minimumPerClass=20)
    return config


@pytest.mark.parametrize("strategy", recent.STRATEGIES)
@pytest.mark.parametrize("window", [None, 3])
def test_disjoint_roles_strict_outcome_cutoff_and_no_later_years(strategy, window):
    frame = source_frame()
    frame.loc[0, "outcomeDate"] = pd.Timestamp("2025-01-01")
    roles, audit = recent.historical_cohorts(frame, strategy, window, minimum=20)
    seen, years = set(), set()
    for cohort in roles.values():
        assert not seen & set(cohort.sourceRowIndex)
        seen.update(cohort.sourceRowIndex)
        assert 0 not in seen
        assert cohort.ApprovalFY.lt(2020).all() and cohort.outcomeDate.lt(recent.CUTOFF).all()
        assert recent.enough_classes(cohort, 20)
        if strategy == "random_years":
            assert not years & set(cohort.ApprovalFY)
            years.update(cohort.ApprovalFY)
    if window:
        assert roles["fit"].ApprovalFY.ge(2017).all()
    if strategy == "random_years":
        assert 2019 in set(roles["fit"].ApprovalFY)  # Five positives cannot form a held-out role.
    assert audit["futureHoldoutIsUntouchedExternalTest"] is False


def test_future_labels_and_outcomes_cannot_change_development_roles():
    frame = source_frame()
    first, _ = recent.historical_cohorts(frame, "random_rows", minimum=20)
    changed = frame.ApprovalFY.ge(2020)
    frame.loc[changed, "LoanStatus"] = 1 - frame.loc[changed, "LoanStatus"]
    frame.loc[changed, "outcomeDate"] = pd.Timestamp("2010-01-01")
    second, _ = recent.historical_cohorts(frame, "random_rows", minimum=20)
    for name in recent.ROLES:
        pd.testing.assert_frame_equal(first[name], second[name])


def test_top100_are_distinct_cold_configurations_and_freeze_exactly_200(tmp_path):
    (tmp_path / "stages").mkdir()
    parents = [parent(i) for i in range(100)]
    duplicate = copy.deepcopy(parents[0])
    duplicate["config"]["window"] = 10
    warm = copy.deepcopy(parents[0])
    warm["config"].update(stage="warm", initArtifact="future-model.joblib")
    configs = recent.frozen_configurations(tmp_path, parents + [duplicate, warm], 100)
    assert len(configs) == len({r["id"] for r in configs}) == 200
    assert {r["splitStrategy"] for r in configs} == set(recent.STRATEGIES)
    assert all("initArtifact" not in c and c["seed"] == c["splitSeed"] == 42 for c in configs)
    assert recent.frozen_configurations(tmp_path, [], 100) == configs
    with pytest.raises(ValueError, match="99 distinct"):
        recent.shortlist_configurations(parents[:99], 100)


@pytest.mark.parametrize("strategy", recent.STRATEGIES)
def test_real_fit_replays_years_pooled_and_common_validation_at_one_threshold(tmp_path, monkeypatch, strategy):
    frame = source_frame()
    monkeypatch.setattr(campaign_fit, "_FRAME", frame)
    monkeypatch.setattr(campaign_fit, "_ROOT", tmp_path)
    previous, writer = campaign_fit.cohort_frames, campaign_fit.write_json
    config = tiny_config(tmp_path, strategy)
    row = recent.run_recent_trial(config)
    assert row["status"] == "complete", row
    assert row["selection"]["constraints"] == {"minPrecision": .55, "minRecall": .85}
    assert row["primaryPolicy"] == "bestPrecisionAtRecallFloor"
    assert campaign_fit.cohort_frames is previous and campaign_fit.write_json is writer
    assert row["audit"]["historicalValidation"]["approvalFiscalYears"] != [2023]
    assert row["audit"]["validation"]["approvalFiscalYears"] == [2023]
    threshold = row["selectionPoint"]["threshold"]
    policy = row["primaryPolicy"]
    for split, cohort in [(str(year), frame.loc[frame.ApprovalFY.eq(year)]) for year in range(2020, 2027)] + [
        ("pooled2020_2026", frame.loc[frame.ApprovalFY.ge(2020)])
    ]:
        probability = artifact_probability(tmp_path, row["artifact"], cohort)
        expected = threshold_table(cohort.LoanStatus, probability, [threshold])[0]
        actual = row["futureHoldout"][split][policy]
        assert [actual[k] for k in ("tp", "fp", "fn", "tn")] == [expected[k] for k in ("tp", "fp", "fn", "tn")]
        assert actual["threshold"] == threshold
    assert row["futureHoldout"]["2026"][policy]["recall"] is None
    pooled = row["futureHoldout"]["pooled2020_2026"][policy]
    assert pooled["tp"] == sum(row["futureHoldout"][str(y)][policy]["tp"] for y in range(2020, 2027))
    assert recent.run_recent_trial(config)["modelSha256"] == row["modelSha256"]
    values = np.load(tmp_path / row["predictions"])
    assert frame.set_index("sourceRowIndex").loc[values["historicalValidationIndices"]].ApprovalFY.lt(2020).all()


def test_failed_future_evaluation_cannot_leave_cacheable_partial_result(tmp_path, monkeypatch):
    monkeypatch.setattr(campaign_fit, "_FRAME", source_frame())
    monkeypatch.setattr(campaign_fit, "_ROOT", tmp_path)
    config = tiny_config(tmp_path, "random_rows")

    def fail(*args):
        saved = json.loads((tmp_path / "trials" / config["id"] / "result.json").read_text())
        assert saved["status"] == "pending_future_evaluation"
        raise ValueError("fixture evaluation failure")

    monkeypatch.setattr(recent, "fixed_evaluation", fail)
    result = recent.run_recent_trial(config)
    assert result["status"] == "failed" and "fixture evaluation failure" in result["error"]
    assert json.loads((tmp_path / "trials" / config["id"] / "result.json").read_text())["status"] == "failed"


def test_real_spawned_stage_exports_both_strategies_and_restores_dispatch(tmp_path, monkeypatch):
    root, export = tmp_path / "run", tmp_path / "export"
    root.mkdir()
    export.mkdir()
    configs = [tiny_config(root, s) for s in recent.STRATEGIES]
    joblib.dump(source_frame(), root / "dataset.joblib")
    write_json(root / "protocol.json", {"cacheSha256": sha256_file(root / "dataset.joblib")})
    write_json(root / "concurrency.json", {"maxActiveFits": 1})
    write_json(root / "recent-holdout-policy.json", {
        "implementationSha256": sha256_file(Path(recent.__file__)), "parentCount": 1, "plannedFitCount": 2})
    monkeypatch.setattr(recent, "frozen_configurations", lambda *args: configs)
    previous = campaign.run_trial
    rows = recent.run_recent_stage(root, export, [parent()])
    assert campaign.run_trial is previous
    assert len(rows) == 2 and all(r["status"] == "complete" for r in rows), rows
    report = json.loads((export / "recent-holdout-results.json").read_text())
    assert report["isUntouchedExternalTest"] is False
    assert report["metricsAreAveraged"] is False
    assert "2026" in (export / "recent-holdout-by-year.csv").read_text()


def test_historical_finalists_do_not_depend_on_future_scores():
    first, second = parent(1), parent(2)
    first["historicalValidation"] = first["validation"]
    second["historicalValidation"] = {"optimal": {"precision": .65, "recall": .8, "f1": .71}}
    before = sorted([first, second], key=recent.historical_rank)
    first["validation"] = {"optimal": {"precision": 1, "recall": 1, "f1": 1}}
    assert sorted([first, second], key=recent.historical_rank) == before


def test_source_and_historical_shortlists_prioritize_current_objective():
    high_f1, high_recall, higher_precision = parent(1), parent(2), parent(3)
    high_f1["validation"] = {"optimal": {"precision": 1., "recall": .6, "f1": .75}}
    high_recall["validation"] = {"optimal": {"precision": .3, "recall": .95, "f1": .456}}
    higher_precision["validation"] = {"optimal": {"precision": .4, "recall": .91, "f1": .556}}
    rows = [high_f1, high_recall, higher_precision]
    assert recent.shortlist_configurations(rows, 1)[0]["sourceId"] == higher_precision["id"]
    for row in rows:
        row["historicalValidation"] = row["validation"]
    assert max(rows, key=recent.historical_rank)["id"] == higher_precision["id"]
