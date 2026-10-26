"""Randomized historical split diagnostics with FY2023 excluded from all fitting."""

import hashlib
import itertools
import shutil
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from scoring_training import campaign_fit
from scoring_training.campaign_data import BUNDLES
from scoring_training.campaign_priority import passes_target, reaches_goal
from scoring_training.campaign_target import new_fit_target
from scoring_training.data import sha256_file
from scoring_training.train import read_json, write_json

STRATEGIES = ("random_rows", "random_years")
SPLIT_SEEDS = (42, 137, 2026)
CUTOFF = pd.Timestamp("2022-10-01")


def mixed_cohorts(frame, strategy, split_seed):
    if strategy not in STRATEGIES:
        raise ValueError("Unknown mixed split strategy")
    historical = frame.ApprovalFY.between(2010, 2020)
    pool = frame.loc[historical & frame.outcomeDate.lt(CUTOFF)].sort_values("sourceRowIndex")
    validation = frame.loc[frame.ApprovalFY.eq(2023)]
    names = ("fit", "early", "calibration", "threshold", "historicalTest")
    groups = {}
    if strategy == "random_rows":
        remaining = pool.index.to_numpy()
        remaining_share = 1.0
        for i, (name, share) in enumerate(zip(names[:-1], (0.70, 0.05, 0.05, 0.10), strict=True)):
            assigned, remaining = train_test_split(
                remaining, train_size=share / remaining_share, random_state=split_seed + i,
                stratify=pool.loc[remaining, "LoanStatus"],
            )
            groups[name] = pool.loc[assigned]
            remaining_share -= share
        groups[names[-1]] = pool.loc[remaining]
    else:
        years = np.random.default_rng(split_seed).permutation(sorted(pool.ApprovalFY.unique()))
        if len(years) < 5:
            raise ValueError("Mixed-year splitting requires at least five fiscal years")
        groups["fit"] = pool.loc[pool.ApprovalFY.isin(years[:-4])]
        for name, year in zip(names[1:], years[-4:], strict=True):
            groups[name] = pool.loc[pool.ApprovalFY.eq(year)]
    groups["validation"] = validation
    audit = {
        "simulationCutoff": str(CUTOFF.date()), "splitStrategy": strategy, "splitSeed": split_seed,
        "historicalPoolRows": len(pool), "historicalPoolPositives": int(pool.LoanStatus.sum()),
        "excludedOutcomeNotKnown": int(historical.sum() - len(pool)),
        "historicalPoolThroughFY": 2020, "futureValidationFY": 2023,
        "historicalTestIsProspective": False,
    }
    seen = set()
    for name, values in groups.items():
        values = values.sort_values(["approvalDate", "sourceRowIndex"]).copy()
        if values.empty or values.LoanStatus.nunique() != 2:
            raise ValueError(f"Insufficient classes in mixed split {name}")
        indices = set(values.sourceRowIndex)
        if indices & seen:
            raise ValueError("Mixed split roles overlap")
        seen.update(indices)
        if name != "validation" and not values.outcomeDate.lt(CUTOFF).all():
            raise ValueError("Future outcome in mixed development")
        groups[name] = values
        audit[name] = {
            "rows": len(values), "positives": int(values.LoanStatus.sum()),
            "approvalFiscalYears": [int(y) for y in sorted(values.ApprovalFY.unique())],
            "firstApproval": str(values.approvalDate.min().date()),
            "lastApproval": str(values.approvalDate.max().date()),
            "sourceIndicesSha256": hashlib.sha256(values.sourceRowIndex.to_numpy(dtype="int64").tobytes()).hexdigest(),
        }
    return groups, audit


def mixed_configurations():
    configurations = []
    splitter_hash = sha256_file(Path(__file__))
    for strategy, split_seed, bundle, balance in itertools.product(
        STRATEGIES, SPLIT_SEEDS, BUNDLES, (1, 3, "SqrtBalanced", "Balanced")
    ):
        configurations.append({
            "id": f"mixed-v1-{len(configurations):04d}", "stage": "mixed", "family": "catboost",
            "fold": "B", "seed": 42, "window": None, "halfLife": None, "balance": balance,
            "bundle": bundle, "parameters": {}, "splitStrategy": strategy, "splitSeed": split_seed,
            "splitterSha256": splitter_hash,
            "targetDefinitionSha256": sha256_file(Path(__file__).with_name("campaign_target.py")),
        })
    return configurations


def run_mixed_trial(config):
    if config["splitterSha256"] != sha256_file(Path(__file__)):
        raise ValueError("Mixed split implementation changed after configuration freeze")
    if config["targetDefinitionSha256"] != sha256_file(Path(__file__).with_name("campaign_target.py")):
        raise ValueError("Mixed fit target changed after configuration freeze")
    cohorts, audit = mixed_cohorts(campaign_fit._FRAME, config["splitStrategy"], config["splitSeed"])
    previous = campaign_fit.cohort_frames

    def fixed_cohorts(frame, fold, window):
        if fold != "B" or window is not None:
            raise ValueError("Unexpected mixed-trial fold/window")
        return cohorts, audit

    campaign_fit.cohort_frames = fixed_cohorts
    try:
        with new_fit_target():
            result = campaign_fit.run_trial(config)
    finally:
        campaign_fit.cohort_frames = previous
    if result["status"] != "complete":
        return result
    root = campaign_fit._ROOT
    saved = joblib.load(root / result["artifact"])
    heldout = cohorts["historicalTest"]
    raw = campaign_fit.raw_prediction(saved["model"], saved["builder"].transform(heldout),
                                     config["family"], saved["categories"])
    probability = saved["calibrator"].predict_proba(raw.reshape(-1, 1))[:, 1]
    if sha256_file(root / "trials" / config["id"] / "selection.json") != result["selectionSha256"]:
        raise ValueError("Mixed-trial threshold changed before historical random evaluation")
    result["historicalRandomTest"] = {
        "rows": len(heldout), "positives": int(heldout.LoanStatus.sum()),
        "policies": campaign_fit.evaluate_points(result["selection"], heldout.LoanStatus, probability),
        "note": "Randomized historical holdout only; future quality is measured separately on FY2023.",
    }
    iid_point = result["historicalRandomTest"]["policies"][result["primaryPolicy"]]
    result["historicalRandomTest"]["targetPassedAtPrimaryPoint"] = reaches_goal(iid_point)
    result["historicalRandomTest"]["acceptablePassedAtPrimaryPoint"] = passes_target(iid_point)
    validation = result["validation"][result["primaryPolicy"]]
    result["validationTargetPassed"] = reaches_goal(validation)
    result["activeTargetPassed"] = passes_target(validation)
    result["splitImplementationSha256"] = config["splitterSha256"]
    path = root / result["predictions"]
    with np.load(path) as stored:
        arrays = {name: stored[name] for name in stored.files}
    arrays.update(historicalTestRaw=raw, historicalTestProbability=probability,
                  historicalTestLabels=heldout.LoanStatus.to_numpy(),
                  historicalTestIndices=heldout.sourceRowIndex.to_numpy())
    np.savez_compressed(path, **arrays)
    write_json(root / "trials" / config["id"] / "result.json", result)
    return result


def run_mixed_stage(root, export):
    """Called after existing fitting pools finish; never exceeds the shared live cap."""
    from scoring_training import campaign
    from scoring_training.campaign_postprocess import export_tables

    if sha256_file(root / "dataset.joblib") != read_json(root / "protocol.json")["cacheSha256"]:
        raise ValueError("Mixed-stage source cache changed")
    policy_path = root / "mixed-policy.json"
    policy = read_json(policy_path) if policy_path.exists() else {}
    configurations = mixed_configurations()
    if policy.get("splitterSha256", sha256_file(Path(__file__))) != sha256_file(Path(__file__)):
        raise ValueError("Mixed-stage implementation differs from the approved policy")
    if policy.get("plannedFitCount", len(configurations)) != len(configurations):
        raise ValueError("Mixed-stage configuration count differs from the approved policy")
    previous = campaign.run_trial
    campaign.run_trial = run_mixed_trial
    try:
        results = campaign.execute_batch(configurations, "mixed", root, workers=3)
    finally:
        campaign.run_trial = previous
    directory = root / "stages" / "mixed-export"
    directory.mkdir(parents=True, exist_ok=True)
    export_tables(directory, results)
    shutil.copyfile(directory / "trials.csv", export / "mixed-trials.csv")
    shutil.copyfile(directory / "operating-points.csv", export / "mixed-operating-points.csv")
    write_json(export / "mixed-results.json", {
        "strategies": list(STRATEGIES), "records": len(results),
        "futureValidationFY": 2023, "futureRowsNeverUsedForFittingOrThresholdSearch": True,
        "weightsMayBePrunedAfterFinalTop10Replay": True,
        "results": [{key: row[key] for key in ("id", "status", "config", "audit", "selection",
                                               "primaryPolicy", "validation", "historicalRandomTest")}
                    if row["status"] == "complete" else row for row in results],
    })
    return results
