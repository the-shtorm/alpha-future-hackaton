"""Calibration variants, thresholded ensembles, immutable comparisons and exports."""

import csv
import itertools
from pathlib import Path

import joblib
import numpy as np
from app.scoring.features import FEATURES
from app.scoring.package import ScoringPackage
from scipy.special import expit
from sklearn.isotonic import IsotonicRegression

from scoring_training.business_thresholds import business_operating_points
from scoring_training.campaign_fit import (
    evaluate_points,
    primary_point,
    raw_prediction,
    result_rank,
    signature,
)
from scoring_training.campaign_retention import retain_top_models, select_top_models
from scoring_training.data import sha256_file
from scoring_training.thresholds import threshold_table
from scoring_training.train import read_json, write_json


def save_composition(root, config, threshold_labels, threshold_probability, validation_labels,
                     validation_probability, artifact, *, threshold_indices=None, validation_indices=None):
    directory = root / "trials" / config["id"]
    directory.mkdir(parents=True, exist_ok=True)
    selection = business_operating_points(threshold_labels, threshold_probability)
    write_json(directory / "selection.json", selection)
    frozen = sha256_file(directory / "selection.json")
    policy, point = primary_point(selection)
    evaluation = evaluate_points(selection, validation_labels, validation_probability)
    joblib.dump(artifact, directory / "model.joblib")
    np.savez_compressed(directory / "predictions.npz", thresholdLabels=threshold_labels,
                        thresholdProbability=threshold_probability, validationLabels=validation_labels,
                        validationProbability=validation_probability, thresholdIndices=threshold_indices,
                        validationIndices=validation_indices)
    row = evaluation[policy]
    result = {
        "id": config["id"], "status": "complete", "config": config, "signature": signature(config),
        "selection": selection, "selectionPoint": point, "primaryPolicy": policy,
        "selectionSha256": frozen, "validation": evaluation,
        "validationTargetPassed": row["precision"] >= 0.6 and row["recall"] >= 0.9,
        "artifact": str((directory / "model.joblib").relative_to(root)),
        "modelSha256": sha256_file(directory / "model.joblib"),
        "predictions": str((directory / "predictions.npz").relative_to(root)),
        "fitSeconds": 0, "deployable": False,
        "postprocessSha256": sha256_file(Path(__file__)),
        "note": "No base-model refit; exact threshold search on this composition's development predictions.",
    }
    assert sha256_file(directory / "selection.json") == frozen
    write_json(directory / "result.json", result)
    return result


def calibration_variants(root, parents):
    results = []
    for parent in parents:
        values = np.load(root / parent["predictions"])
        for method in ("none", "isotonic"):
            config = {**parent["config"], "id": f"cal-{parent['id']}-{method}", "stage": "calibration",
                      "parent": parent["id"], "calibrationMethod": method}
            if method == "isotonic":
                calibrator = IsotonicRegression(out_of_bounds="clip").fit(values["calibrationRaw"],
                                                                         values["calibrationLabels"])
                threshold = calibrator.predict(values["thresholdRaw"])
                validation = calibrator.predict(values["validationRaw"])
            else:
                calibrator = None
                threshold, validation = expit(values["thresholdRaw"]), expit(values["validationRaw"])
            results.append(save_composition(
                root, config, values["thresholdLabels"], threshold, values["validationLabels"], validation,
                {"kind": "recalibrated", "base": parent["artifact"], "calibrator": calibrator},
                threshold_indices=values["thresholdIndices"], validation_indices=values["validationIndices"],
            ))
    return results


def blend_candidates(root, parents, robust_results):
    lookup = {(row["config"].get("parent"), row["config"]["fold"]): row for row in robust_results
              if row.get("status") == "complete" and row["config"]["seed"] == 42}
    results = []
    for pair_index, (left, right) in enumerate(list(itertools.combinations(parents[:5], 2))[:5]):
        for weight in (0.1, 0.25, 0.5, 0.75, 0.9):
            for fold in ("A", "B", "C"):
                a = left if fold == "B" else lookup.get((left["id"], fold))
                b = right if fold == "B" else lookup.get((right["id"], fold))
                if a is None or b is None:
                    continue
                av, bv = np.load(root / a["predictions"]), np.load(root / b["predictions"])
                for field in ("thresholdIndices", "validationIndices", "thresholdLabels", "validationLabels"):
                    if not np.array_equal(av[field], bv[field]):
                        raise ValueError("Ensemble component row alignment mismatch")
                config = {**left["config"], "id": f"blend-{pair_index}-{weight:g}-{fold}", "stage": "ensembles",
                          "family": "blend", "fold": fold, "parent": [a["id"], b["id"]],
                          "components": [a["signature"], b["signature"]], "blendWeight": weight}
                results.append(save_composition(
                    root, config, av["thresholdLabels"],
                    weight * av["thresholdProbability"] + (1 - weight) * bv["thresholdProbability"],
                    av["validationLabels"],
                    weight * av["validationProbability"] + (1 - weight) * bv["validationProbability"],
                    {"kind": "blend", "left": a["artifact"], "right": b["artifact"], "weight": weight},
                    threshold_indices=av["thresholdIndices"], validation_indices=av["validationIndices"],
                ))
    return results


def artifact_probability(root, artifact_path, frame):
    saved = joblib.load(root / artifact_path)
    if saved.get("kind") == "blend":
        return (saved["weight"] * artifact_probability(root, saved["left"], frame)
                + (1 - saved["weight"]) * artifact_probability(root, saved["right"], frame))
    if saved.get("kind") == "recalibrated":
        base = joblib.load(root / saved["base"])
        raw = raw_prediction(base["model"], base["builder"].transform(frame), base["config"]["family"],
                             base["categories"])
        return expit(raw) if saved["calibrator"] is None else saved["calibrator"].predict(raw)
    raw = raw_prediction(saved["model"], saved["builder"].transform(frame), saved["config"]["family"],
                         saved["categories"])
    return saved["calibrator"].predict_proba(raw.reshape(-1, 1))[:, 1]


def metrics_for_frame(frame, probability, threshold):
    row = threshold_table(frame.LoanStatus, probability, [threshold])[0]
    row["recallDefined"] = bool(row["positives"])
    if not row["recallDefined"]:
        row["recall"] = None
    return row


def future_diagnostics(root, winner, safe_winner, export, top_candidates=None):
    frame = joblib.load(root / "dataset.joblib")
    favorite = read_json(export / "favorite.json")
    original = ScoringPackage(root / "favorite-package", favorite["manifestSha256"])
    results = {}
    candidates = {"bestOverall": winner, "bestWithoutTerm": safe_winner,
                  **{row["id"]: row for row in top_candidates or []}}
    for year in (2023, 2024, 2025, 2026):
        cohort = frame.loc[frame.ApprovalFY.eq(year)]
        rows = {"favorite": metrics_for_frame(cohort, original.predict_frame(cohort[list(FEATURES)]),
                                              favorite["threshold"])}
        predictions = {}
        for name, candidate in candidates.items():
            if candidate["artifact"] not in predictions:
                predictions[candidate["artifact"]] = artifact_probability(root, candidate["artifact"], cohort)
            rows[name] = metrics_for_frame(cohort, predictions[candidate["artifact"]],
                                          candidate["selectionPoint"]["threshold"])
        results[str(year)] = rows
    write_json(export / "fixed-future-diagnostics.json", {
        "note": "Historical previously inspected completed-loan cohorts; not a fresh external test. No retuning.",
        "results": results,
    })
    return results


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def brief(row):
    return {key: row[key] for key in ("id", "config", "status", "primaryPolicy", "selectionPoint", "selection",
                                     "validation", "validationTargetPassed", "artifact", "modelSha256")}


def export_tables(export, results):
    summary, points = [], []
    for result in results:
        config = result["config"]
        base = {"trial": result["id"], "stage": config["stage"], "family": config["family"],
                "bundle": config["bundle"], "fold": config["fold"], "seed": config["seed"],
                "window": config.get("window"), "halfLife": config.get("halfLife"),
                "balance": config.get("balance"), "status": result["status"]}
        row = {**base, "selectionStatus": None, "policy": None, "threshold": None,
               "selectionPrecision": None, "selectionF1": None, "selectionRecall": None,
               "validationPrecision": None, "validationF1": None, "validationRecall": None,
               "validationTargetPassed": False, "TP": None, "FP": None, "FN": None,
               "fitSeconds": result.get("fitSeconds"), "reusedFrom": result.get("reusedFrom"),
               "modelSha256": result.get("modelSha256"), "error": result.get("error")}
        if result["status"] == "complete":
            selection, validation = result["selectionPoint"], result["validation"][result["primaryPolicy"]]
            row.update(selectionStatus=result["selection"]["status"], policy=result["primaryPolicy"],
                       threshold=selection["threshold"], selectionPrecision=selection["precision"],
                       selectionF1=selection["f1"], selectionRecall=selection["recall"],
                       validationPrecision=validation["precision"], validationF1=validation["f1"],
                       validationRecall=validation["recall"], validationTargetPassed=result["validationTargetPassed"],
                       TP=validation["tp"], FP=validation["fp"], FN=validation["fn"])
            for policy in ("optimal", "bestRecallAtPrecisionFloor", "bestPrecisionAtRecallFloor",
                           "unconstrainedMaximumF1"):
                point = result["selection"][policy]
                for split, metrics in (("selection", point), ("validation", result["validation"].get(policy))):
                    points.append({**base, "policy": policy, "split": split,
                                   "threshold": metrics["threshold"] if metrics else None,
                                   "precision": metrics["precision"] if metrics else None,
                                   "f1": metrics["f1"] if metrics else None,
                                   "recall": metrics["recall"] if metrics else None,
                                   "TP": metrics["tp"] if metrics else None,
                                   "FP": metrics["fp"] if metrics else None,
                                   "FN": metrics["fn"] if metrics else None})
        summary.append(row)
    write_csv(export / "trials.csv", summary)
    write_csv(export / "operating-points.csv", points)


def plot_results(export, candidates, winner, safe_winner, diagnostics):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    figure, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    for bundle, color in (("original9_diagnostic_term_unconfirmed", "#bd7832"),
                          ("safe8_without_term", "#2176ae"), ("engineered_safe8", "#2d9270")):
        rows = [row["validation"][row["primaryPolicy"]] for row in candidates if row["config"]["bundle"] == bundle]
        axes[0].scatter([r["precision"] for r in rows], [r["recall"] for r in rows],
                        s=12, alpha=0.45, color=color, label=bundle.split("_")[0])
    axes[0].add_patch(Rectangle((0.6, 0.9), 0.4, 0.1, color="green", alpha=0.15))
    axes[0].set(title="FY2023: each candidate at its frozen threshold", xlabel="Precision", ylabel="Recall")
    for name, color, candidate in (("best", "black", winner), ("safe", "blue", safe_winner)):
        row = candidate["validation"][candidate["primaryPolicy"]]
        axes[0].scatter([row["precision"]], [row["recall"]], marker="*", s=120, color=color, label=name)
    for name, marker in (("favorite", "o"), ("bestOverall", "s"), ("bestWithoutTerm", "^")):
        years = [int(y) for y, rows in diagnostics.items() if rows[name]["recallDefined"]]
        axes[1].plot(years, [diagnostics[str(y)][name]["recall"] for y in years], marker=marker, label=name)
    axes[1].axhline(0.9, color="gray", linestyle="--")
    axes[1].set(title="Fixed-threshold recall; completed-loan population", xlabel="Approval FY", ylabel="Recall")
    for axis in axes:
        axis.set_ylim(0, 1.02)
        axis.grid(alpha=0.2)
        axis.legend(fontsize=8)
    axes[0].set_xlim(0, 1.02)
    figure.tight_layout()
    figure.savefig(export / "campaign-tradeoffs.png", dpi=170)
    plt.close(figure)


def postprocess(root, export, results, parents):
    robust = [r for r in results if r["config"]["stage"] == "robustness"]
    variants = calibration_variants(root, parents)
    blends = blend_candidates(root, parents, robust)
    results = results + variants + blends
    write_json(root / "stages" / "postprocess-results.json", variants + blends)
    eligible = [r for r in results if r.get("status") == "complete" and r["config"]["fold"] == "B"
                and r["config"]["seed"] == 42]
    ranked = sorted(eligible, key=result_rank, reverse=True)
    favorite = read_json(export / "favorite-validation.json")["byFold"]["B"]["metrics"]
    top10, improved_count = select_top_models(root, eligible, favorite)
    winner = top10[0]
    safe = [r for r in ranked if r["config"]["bundle"] != "original9_diagnostic_term_unconfirmed"]
    # A mixed ensemble is safe only when both components were safe.
    safe = [r for r in safe if r["config"]["family"] != "blend"
            or all(next(p for p in parents if p["id"] == source)["config"]["bundle"] !=
                   "original9_diagnostic_term_unconfirmed" for source in r["config"]["parent"])]
    safe_selected, _ = select_top_models(root, safe, favorite, limit=1)
    safe_winner = safe_selected[0]
    export_tables(export, results)
    diagnostics = future_diagnostics(root, winner, safe_winner, export, top10)
    plot_results(export, eligible, winner, safe_winner, diagnostics)
    retention_policy = read_json(root / "retention-policy.json") if (root / "retention-policy.json").exists() else {}
    retention = None
    if retention_policy.get("deleteOtherWeights") is True:
        retention = retain_top_models(root, top10, lambda path, frame: artifact_probability(root, path, frame))
        write_json(export / "retention.json", retention)
    top_rows = []
    for rank, row in enumerate(top10, 1):
        point = row["validation"][row["primaryPolicy"]]
        top_rows.append({"rank": rank, "id": row["id"], "family": row["config"]["family"],
                         "bundle": row["config"]["bundle"], "validationFY": 2023,
                         "threshold": point["threshold"], "precision": point["precision"],
                         "f1": point["f1"], "recall": point["recall"], "TP": point["tp"], "FP": point["fp"],
                         "FN": point["fn"], "goalPassed": row["validationTargetPassed"],
                         "deltaPrecision": point["precision"] - favorite["precision"],
                         "deltaF1": point["f1"] - favorite["f1"],
                         "deltaRecall": point["recall"] - favorite["recall"],
                         "primaryPolicy": row["primaryPolicy"], "artifact": row["artifact"],
                         "modelSha256": row["modelSha256"]})
    write_csv(export / "top10.csv", top_rows)
    write_json(export / "top10.json", {"favorite": favorite, "sameCohort": True,
                                       "distinctValidationDecisions": True,
                                       "ranking": "goal passed first, then F1, recall, precision; only improvements if any",
                                       "candidates": [brief(row) for row in top10]})
    leaders = {"bestOverall": brief(winner), "bestWithoutTerm": brief(safe_winner),
               "closestToBothFloors": brief(ranked[0]), "top20ByConstraintProximity": [brief(r) for r in ranked[:20]]}
    if retention:
        for row in [leaders["bestOverall"], leaders["bestWithoutTerm"], leaders["closestToBothFloors"],
                    *leaders["top20ByConstraintProximity"]]:
            row["artifactRetained"] = row["artifact"] in retention["retainedModelFiles"]
    write_json(export / "leaders.json", leaders)
    family_counts = {}
    for result in results:
        family = result["config"]["family"]
        counts = family_counts.setdefault(family, {"records": 0, "complete": 0, "failed": 0})
        counts["records"] += 1
        counts["complete" if result["status"] == "complete" else "failed"] += 1
    summary = {
        "status": "complete_with_failures" if any(r["status"] != "complete" for r in results) else "complete",
        "recordCount": len(results), "familyCounts": family_counts,
        "distinctBaseModelArtifacts": len({r["artifact"] for r in results
                                            if r.get("status") == "complete" and r["config"]["stage"] not in
                                            ("calibration", "ensembles")}),
        "failedRecords": [{"id": r["id"], "error": r["error"]} for r in results if r["status"] != "complete"],
        "metricsAreAveraged": False, "favoriteRetained": True, "deploymentChanged": False,
        "improvedRecordCount": improved_count, "top10Count": len(top10),
        "retentionCompleted": bool(retention and retention["cleanupComplete"]),
        "bestId": winner["id"], "bestWithoutTermId": safe_winner["id"],
        "protocolSha256": sha256_file(export / "protocol.json"),
        "limitations": ["Completed-loan selection bias remains.", "Original term history is unconfirmed.",
                        "Validation cohorts were historically inspected; this is not a fresh external test.",
                        "Maturation gap and validation years explicitly revise the original proposal.",
                        "Each operating point uses one threshold; no fold or threshold metric averaging."],
    }
    write_json(export / "summary.json", summary)
    write_json(export / "artifact-hashes.json", {p.name: sha256_file(p) for p in export.iterdir()
                                                 if p.is_file() and p.name != "artifact-hashes.json"})
    write_json(root / "progress.json", {"stage": "complete", "summary": summary})
    print(f"CAMPAIGN COMPLETE: {winner['id']} / {safe_winner['id']}", flush=True)
