"""Mixed-year and mixed-row diagnostics keep every FY2023 loan outside fitting."""

import json

import joblib
import numpy as np
import pandas as pd
import pytest
from scoring_training import campaign, campaign_fit, campaign_mixed
from scoring_training.campaign_mixed import CUTOFF, mixed_cohorts, mixed_configurations, run_mixed_trial
from scoring_training.campaign_postprocess import artifact_probability
from scoring_training.data import sha256_file
from scoring_training.tests.test_campaign_data import sample
from scoring_training.thresholds import threshold_table
from scoring_training.train import write_json


def frame():
    values = pd.concat([sample()] * 30, ignore_index=True)
    values["sourceRowIndex"] = np.arange(len(values))
    # One past approval's outcome would not have been known at the simulated date.
    values.loc[0, "outcomeDate"] = pd.Timestamp("2025-01-01")
    return values


@pytest.mark.parametrize("strategy", ["random_rows", "random_years"])
@pytest.mark.parametrize("seed", [42, 137, 2026])
def test_all_roles_disjoint_known_before_cutoff_and_future_cohort_unchanged(strategy, seed):
    source = frame()
    roles, audit = mixed_cohorts(source, strategy, seed)
    expected = source.loc[source.ApprovalFY.eq(2023)].sourceRowIndex
    np.testing.assert_array_equal(roles["validation"].sourceRowIndex, expected)
    seen = set()
    for name, values in roles.items():
        assert not set(values.sourceRowIndex) & seen
        seen.update(values.sourceRowIndex)
        if name != "validation":
            assert values.ApprovalFY.le(2020).all()
            assert values.outcomeDate.lt(CUTOFF).all()
            assert 0 not in set(values.sourceRowIndex)
    assert audit["historicalTestIsProspective"] is False
    if strategy == "random_years":
        assert roles["fit"].ApprovalFY.nunique() == 7
        for name in ("early", "calibration", "threshold", "historicalTest"):
            assert roles[name].ApprovalFY.nunique() == 1
        development_years = [set(roles[name].ApprovalFY) for name in roles if name != "validation"]
        assert sum(map(len, development_years)) == len(set.union(*development_years)) == 11
    else:
        assert roles["fit"].ApprovalFY.nunique() == 11
        assert roles["historicalTest"].ApprovalFY.nunique() > 1


def test_future_labels_cannot_change_historical_assignments_or_threshold_pool():
    source = frame()
    first, _ = mixed_cohorts(source, "random_rows", 42)
    source.loc[source.ApprovalFY.eq(2023), "LoanStatus"] = 1 - source.loc[
        source.ApprovalFY.eq(2023), "LoanStatus"
    ]
    second, _ = mixed_cohorts(source, "random_rows", 42)
    for name in ("fit", "early", "calibration", "threshold", "historicalTest"):
        pd.testing.assert_frame_equal(first[name], second[name])


def test_configuration_count_and_distinct_split_seeds_are_explicit():
    configurations = mixed_configurations()
    assert len(configurations) == 72
    assert {row["seed"] for row in configurations} == {42}
    assert {row["splitSeed"] for row in configurations} == {42, 137, 2026}
    assert len({row["id"] for row in configurations}) == 72


@pytest.mark.parametrize("strategy", ["random_rows", "random_years"])
def test_real_mixed_fit_scores_both_holdouts_at_one_frozen_threshold(tmp_path, monkeypatch, strategy):
    source = frame()
    monkeypatch.setattr(campaign_fit, "_FRAME", source)
    monkeypatch.setattr(campaign_fit, "_ROOT", tmp_path)
    previous = campaign_fit.cohort_frames
    config = next(row for row in mixed_configurations()
                  if row["splitStrategy"] == strategy and row["bundle"] == "safe8_without_term")
    config["parameters"] = {"iterations": 5}
    result = run_mixed_trial(config)
    assert result["status"] == "complete", result
    assert campaign_fit.cohort_frames is previous
    roles, _ = mixed_cohorts(source, strategy, config["splitSeed"])
    policy = result["primaryPolicy"]
    threshold = result["selectionPoint"]["threshold"]
    for role in ("historicalTest", "validation"):
        probability = artifact_probability(tmp_path, result["artifact"], roles[role])
        direct = threshold_table(roles[role].LoanStatus, probability, [threshold])[0]
        stored = (result["historicalRandomTest"]["policies"] if role == "historicalTest" else result["validation"])[policy]
        assert direct == stored
    assert json.loads((tmp_path / "trials" / config["id"] / "selection.json").read_text()) == result["selection"]
    assert run_mixed_trial(config)["modelSha256"] == result["modelSha256"]


def test_real_spawned_batch_runs_both_strategies_and_restores_base_dispatch(tmp_path, monkeypatch):
    root, export = tmp_path / "run", tmp_path / "export"
    root.mkdir()
    export.mkdir()
    joblib.dump(frame(), root / "dataset.joblib")
    write_json(root / "protocol.json", {"cacheSha256": sha256_file(root / "dataset.joblib")})
    write_json(root / "concurrency.json", {"maxActiveFits": 1})
    configurations = []
    for strategy in ("random_rows", "random_years"):
        value = next(row for row in mixed_configurations()
                     if row["splitStrategy"] == strategy and row["bundle"] == "safe8_without_term")
        value["parameters"] = {"iterations": 5}
        configurations.append(value)
    monkeypatch.setattr(campaign_mixed, "mixed_configurations", lambda: configurations)
    base_dispatch = campaign.run_trial
    results = campaign_mixed.run_mixed_stage(root, export)
    assert campaign.run_trial is base_dispatch
    assert len(results) == 2 and all(row["status"] == "complete" for row in results)
    assert {row["config"]["splitStrategy"] for row in results} == {"random_rows", "random_years"}
    assert all("historicalRandomTest" in row for row in results)
    assert json.loads((export / "mixed-results.json").read_text())["records"] == 2
    assert "historicalTestPrecision" in (export / "mixed-trials.csv").read_text()
