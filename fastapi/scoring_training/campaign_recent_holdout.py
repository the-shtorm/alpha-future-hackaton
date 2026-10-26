"""Refit 100 frozen configurations on shuffled pre-2020 development roles."""

import hashlib
import json
import traceback
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from scoring_training import campaign_fit
from scoring_training.campaign_priority import (
    RANKING,
    passes_recall_floor,
    passes_target,
    reaches_goal,
    recall_rank,
    recall_rank_values,
)
from scoring_training.campaign_target import new_fit_target
from scoring_training.data import sha256_file
from scoring_training.train import read_json, write_json

CUTOFF = pd.Timestamp("2019-10-01")
STRATEGIES = ("random_rows", "random_years")
ROLES = ("fit", "early", "calibration", "threshold", "validation")
FAMILIES = ("catboost", "lightgbm", "xgboost", "logistic", "randomForest")


def enough_classes(values, minimum):
    return all(int(values.LoanStatus.eq(label).sum()) >= minimum for label in (0, 1))


def historical_cohorts(frame, strategy, window=None, split_seed=42, minimum=100):
    if strategy not in STRATEGIES:
        raise ValueError("Unknown historical shuffle strategy")
    historical = frame.ApprovalFY.between(2010, 2019)
    pool = frame.loc[historical & frame.outcomeDate.lt(CUTOFF)].sort_values("sourceRowIndex")
    attempts = 1
    if strategy == "random_rows":
        remaining, share_left, groups = pool.index.to_numpy(), 1.0, {}
        for i, (name, share) in enumerate(zip(ROLES[:-1], (.70, .05, .05, .10), strict=True)):
            assigned, remaining = train_test_split(
                remaining, train_size=share / share_left, random_state=split_seed + i,
                stratify=pool.loc[remaining, "LoanStatus"],
            )
            groups[name] = pool.loc[assigned]
            share_left -= share
        groups["validation"] = pool.loc[remaining]
    else:
        years = sorted(pool.ApprovalFY.unique())
        if len(years) < 5:
            raise ValueError("At least five historical fiscal years required")
        rng = np.random.default_rng(split_seed)
        for attempt in range(1000):
            attempts = attempt + 1
            shuffled = rng.permutation(years)
            groups = {"fit": pool.loc[pool.ApprovalFY.isin(shuffled[:-4])]}
            groups.update({name: pool.loc[pool.ApprovalFY.eq(year)]
                           for name, year in zip(ROLES[1:], shuffled[-4:], strict=True)})
            fit = groups["fit"]
            if window:
                fit = fit.loc[fit.ApprovalFY.ge(2020 - window)]
            if enough_classes(fit, minimum) and all(enough_classes(groups[n], minimum) for n in ROLES[1:]):
                break
        else:
            raise ValueError("No whole-year split with sufficient pre-2020 class support")
    if window:
        groups["fit"] = groups["fit"].loc[groups["fit"].ApprovalFY.ge(2020 - window)]
    audit = {
        "simulationCutoff": str(CUTOFF.date()), "splitStrategy": strategy, "splitSeed": split_seed,
        "minimumPerClass": minimum, "assignmentAttempts": attempts,
        "historicalPoolRows": len(pool), "historicalPoolPositives": int(pool.LoanStatus.sum()),
        "excludedOutcomeNotKnown": int(historical.sum() - len(pool)),
        "fitWindowThroughFY": 2019, "futureHoldoutFYs": list(range(2020, 2027)),
        "futureHoldoutIsUntouchedExternalTest": False,
    }
    seen = set()
    for name in ROLES:
        values = groups[name].sort_values(["approvalDate", "sourceRowIndex"]).copy()
        if not enough_classes(values, minimum):
            raise ValueError(f"Insufficient class support in historical {name}")
        indices = set(values.sourceRowIndex)
        if seen & indices or not values.ApprovalFY.lt(2020).all() or not values.outcomeDate.lt(CUTOFF).all():
            raise ValueError("Historical roles overlap or contain future loans/outcomes")
        seen.update(indices)
        groups[name] = values
        audit[name] = {
            "rows": len(values), "positives": int(values.LoanStatus.sum()),
            "approvalFiscalYears": [int(y) for y in sorted(values.ApprovalFY.unique())],
            "sourceIndicesSha256": hashlib.sha256(values.sourceRowIndex.to_numpy(dtype="int64").tobytes()).hexdigest(),
        }
    return groups, audit


def configuration_template(config):
    """Transfer fit settings only; never transfer an already-trained checkpoint."""
    window = config.get("window")
    return {
        "family": config["family"], "bundle": config["bundle"],
        "parameters": config.get("parameters", {}), "balance": config.get("balance", 1),
        "halfLife": config.get("halfLife"), "window": None if window is None or window >= 10 else window,
    }


def shortlist_configurations(results, count=100):
    eligible = [r for r in results if r.get("status") == "complete" and r["config"]["fold"] == "B"
                and r["config"]["seed"] == 42 and r["config"]["family"] in FAMILIES
                and r["config"]["stage"] in ("screening", "refinement", "competitors")
                and not r["config"].get("initArtifact")
                and passes_recall_floor(r["validation"][r["primaryPolicy"]])]

    selected, seen = [], set()
    for row in sorted(eligible, key=lambda r: (*recall_rank(r), r["id"]), reverse=True):
        template = configuration_template(row["config"])
        digest = hashlib.sha256(json.dumps(template, sort_keys=True).encode()).hexdigest()
        if digest not in seen:
            selected.append({"sourceId": row["id"], "templateSha256": digest, "template": template})
            seen.add(digest)
        if len(selected) == count:
            return selected
    raise ValueError(f"Only {len(selected)} distinct eligible configurations; {count} required")


def frozen_configurations(root, results, count):
    path = root / "stages" / "recent-holdout-shortlist.json"
    implementation = sha256_file(Path(__file__))
    if path.exists():
        frozen = read_json(path)
        if frozen["implementationSha256"] != implementation or len(frozen["parents"]) != count:
            raise ValueError("Frozen recent-holdout shortlist differs from the policy")
    else:
        frozen = {"implementationSha256": implementation, "parents": shortlist_configurations(results, count),
                  "ranking": RANKING,
                  "selectionUsesPreviouslyInspectedFY2023": True,
                  "note": "Adaptive historical benchmark, not untouched external testing."}
        write_json(path, frozen)
    configs = []
    for rank, parent in enumerate(frozen["parents"]):
        for strategy in STRATEGIES:
            configs.append({**parent["template"], "id": f"recent-v1-{rank:03d}-{strategy}",
                            "stage": "recent_holdout", "fold": "B", "seed": 42, "splitSeed": 42,
                            "splitStrategy": strategy, "parent": parent["sourceId"],
                            "minimumPerClass": 100, "historicalFitThroughFY": 2019,
                            "holdoutImplementationSha256": implementation})
            configs[-1]["targetDefinitionSha256"] = sha256_file(Path(__file__).with_name("campaign_target.py"))
    return configs


def fixed_evaluation(selection, frame, probability):
    result = campaign_fit.evaluate_points(selection, frame.LoanStatus, probability)
    for point in result.values():
        point["recallDefined"] = bool(point["positives"])
        if not point["recallDefined"]:
            point["recall"] = None
    return result


def run_recent_trial(config):
    try:
        return _run_recent_trial(config)
    except Exception as error:
        result = {"id": config["id"], "config": config, "status": "failed",
                  "signature": campaign_fit.signature(config),
                  "error": f"{type(error).__name__}: {error}", "traceback": traceback.format_exc()}
        directory = campaign_fit._ROOT / "trials" / config["id"]
        directory.mkdir(parents=True, exist_ok=True)
        write_json(directory / "result.json", result)
        return result


def _run_recent_trial(config):
    if config["holdoutImplementationSha256"] != sha256_file(Path(__file__)):
        raise ValueError("Recent-holdout implementation changed")
    if config["targetDefinitionSha256"] != sha256_file(Path(__file__).with_name("campaign_target.py")):
        raise ValueError("Recent-holdout target changed")
    cohorts, audit = historical_cohorts(campaign_fit._FRAME, config["splitStrategy"], config.get("window"),
                                       config["splitSeed"], config["minimumPerClass"])
    previous = campaign_fit.cohort_frames
    previous_writer = campaign_fit.write_json
    result_path = campaign_fit._ROOT / "trials" / config["id"] / "result.json"

    def pending_writer(path, value):
        # A restart must never reuse a base fit as a fully evaluated holdout trial.
        if path == result_path and value.get("status") == "complete" and "futureHoldout" not in value:
            value = {**value, "status": "pending_future_evaluation"}
        previous_writer(path, value)

    campaign_fit.cohort_frames = lambda *args: (cohorts, audit)
    campaign_fit.write_json = pending_writer
    try:
        with new_fit_target():
            result = campaign_fit.run_trial(config)
    finally:
        campaign_fit.cohort_frames = previous
        campaign_fit.write_json = previous_writer
    if result["status"] != "complete" or "futureHoldout" in result:
        return result
    root = campaign_fit._ROOT
    with np.load(root / result["predictions"]) as stored:
        arrays = {name: stored[name] for name in stored.files}
    historical = result["validation"]
    for name in list(arrays):
        if name.startswith("validation"):
            arrays[name.replace("validation", "historicalValidation", 1)] = arrays.pop(name)
    future = campaign_fit._FRAME.loc[campaign_fit._FRAME.ApprovalFY.between(2020, 2026)].sort_values(
        ["approvalDate", "sourceRowIndex"])
    saved = joblib.load(root / result["artifact"])
    raw = campaign_fit.raw_prediction(saved["model"], saved["builder"].transform(future),
                                     config["family"], saved["categories"])
    probability = saved["calibrator"].predict_proba(raw.reshape(-1, 1))[:, 1]
    if sha256_file(root / "trials" / config["id"] / "selection.json") != result["selectionSha256"]:
        raise ValueError("Threshold changed before future evaluation")
    tests = {"pooled2020_2026": fixed_evaluation(result["selection"], future, probability)}
    for year in range(2020, 2027):
        mask = future.ApprovalFY.eq(year).to_numpy()
        if mask.any():
            tests[str(year)] = fixed_evaluation(result["selection"], future.loc[mask], probability[mask])
    common = future.ApprovalFY.eq(2023).to_numpy()
    result["historicalValidation"] = historical
    result["futureHoldout"] = tests
    result["validation"] = tests["2023"]
    point = result["validation"][result["primaryPolicy"]]
    result["validationTargetPassed"] = reaches_goal(point)
    result["activeTargetPassed"] = passes_target(point)
    result["audit"]["historicalValidation"] = result["audit"]["validation"]
    result["audit"]["validation"] = {"rows": int(common.sum()),
                                         "positives": int(future.loc[common, "LoanStatus"].sum()),
                                         "approvalFiscalYears": [2023]}
    result["note"] = "All fit/calibration/threshold/validation development roles predate FY2020. Later-year selection is adaptive historical evaluation."
    arrays.update(validationRaw=raw[common], validationProbability=probability[common],
                  validationLabels=future.loc[common, "LoanStatus"].to_numpy(),
                  validationIndices=future.loc[common, "sourceRowIndex"].to_numpy(),
                  futureHoldoutProbability=probability, futureHoldoutLabels=future.LoanStatus.to_numpy(),
                  futureHoldoutIndices=future.sourceRowIndex.to_numpy())
    np.savez_compressed(root / result["predictions"], **arrays)
    write_json(root / "trials" / config["id"] / "result.json", result)
    return result


def historical_rank(row):
    p = row["historicalValidation"][row["primaryPolicy"]]
    return (*recall_rank_values(p), row["id"])


def run_recent_stage(root, export, source_results):
    from scoring_training import campaign
    from scoring_training.campaign_postprocess import export_tables, write_csv

    policy = read_json(root / "recent-holdout-policy.json")
    if policy["implementationSha256"] != sha256_file(Path(__file__)):
        raise ValueError("Recent-holdout policy code hash differs")
    if sha256_file(root / "dataset.joblib") != read_json(root / "protocol.json")["cacheSha256"]:
        raise ValueError("Recent-holdout dataset cache changed")
    configs = frozen_configurations(root, source_results, policy["parentCount"])
    if len(configs) != policy["plannedFitCount"]:
        raise ValueError("Recent-holdout fit count differs from approved policy")
    previous = campaign.run_trial
    campaign.run_trial = run_recent_trial
    try:
        results = campaign.execute_batch(configs, "recent_holdout", root, workers=3)
    finally:
        campaign.run_trial = previous
    export_tables(root / "stages", results)
    for source, name in (("trials.csv", "recent-holdout-trials.csv"),
                         ("operating-points.csv", "recent-holdout-operating-points.csv")):
        (export / name).write_bytes((root / "stages" / source).read_bytes())
    good = [r for r in results if r["status"] == "complete"]
    development_eligible = [r for r in good if passes_target(r["historicalValidation"][r["primaryPolicy"]])]
    development_top = [r["id"] for r in sorted(development_eligible, key=historical_rank, reverse=True)[:10]]
    write_json(export / "recent-holdout-results.json", {
        "records": len(results), "parentCount": policy["parentCount"],
        "futureFYsExcludedFromFitting": list(range(2020, 2027)),
        "isUntouchedExternalTest": False, "historicalValidationTop10": development_top,
        "historicalValidationRankingDoesNotUseFutureMetrics": True, "metricsAreAveraged": False,
        "shortlist": read_json(root / "stages" / "recent-holdout-shortlist.json"), "results": results,
    })
    points = []
    for row in good:
        for split, values in {"historicalValidation": row["historicalValidation"], **row["futureHoldout"]}.items():
            for name, point in values.items():
                points.append({"id": row["id"], "splitStrategy": row["config"]["splitStrategy"],
                               "split": split, "policy": name, **point,
                               "recallDefined": bool(point["positives"])})
    write_csv(export / "recent-holdout-by-year.csv", points,
              ["id", "splitStrategy", "split", "policy", "threshold", "precision", "f1", "recall"])
    return results
