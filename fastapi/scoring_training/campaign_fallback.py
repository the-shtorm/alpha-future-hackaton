"""Finalize substantial favorite improvements only after an unsuccessful full target search."""

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path

import joblib
import numpy as np

from scoring_training.campaign import protect_favorite
from scoring_training.campaign_postprocess import (
    artifact_probability,
    brief,
    future_diagnostics,
    plot_results,
    write_csv,
)
from scoring_training.campaign_priority import passes_target, reaches_goal
from scoring_training.campaign_retention import retain_top_models
from scoring_training.data import sha256_file
from scoring_training.train import read_json, write_json

RANKING = "substantial favorite improvements below target: recall, then precision, then F1"
CRITERIA = {"minRecallGain": .10, "minF1Gain": .05, "noMetricRegression": True}
REQUIRED_STAGES = {"screening": 480, "refinement": 360, "competitors": 168, "warm": 24,
                   "robustness": 90, "mixed": 72, "recent_holdout": 200}


def select_substantial_improvements(root, candidates, favorite, limit=10):
    eligible = []
    for row in candidates:
        if row.get("status") != "complete":
            continue
        point = row["validation"][row["primaryPolicy"]]
        if (all(point[k] >= favorite[k] for k in ("precision", "recall", "f1"))
                and point["recall"] - favorite["recall"] >= CRITERIA["minRecallGain"] - 1e-12
                and point["f1"] - favorite["f1"] >= CRITERIA["minF1Gain"] - 1e-12):
            eligible.append(row)

    def rank(row):
        p = row["validation"][row["primaryPolicy"]]
        safe = row["config"]["bundle"] != "original9_diagnostic_term_unconfirmed"
        calibrated = row["config"].get("calibrationMethod") != "none"
        return p["recall"], p["precision"], p["f1"], safe, calibrated

    selected, decisions = [], set()
    for row in sorted(eligible, key=rank, reverse=True):
        with np.load(root / row["predictions"]) as values:
            flagged = values["validationProbability"] >= row["selectionPoint"]["threshold"]
            digest = hashlib.sha256(values["validationIndices"].tobytes() + np.packbits(flagged).tobytes()).hexdigest()
        if digest not in decisions:
            selected.append(row)
            decisions.add(digest)
        if len(selected) == limit:
            break
    return selected, len(eligible)


def finished_program_results(root, export):
    progress = read_json(root / "progress.json")
    original = export / "target-only-summary.json"
    resumed = (root / "fallback-plan.json").exists() and original.exists()
    summary = read_json(original if resumed else export / "summary.json")
    if progress.get("stage") != "complete" or summary["status"] != "complete_no_feasible":
        raise ValueError("Fallback requires a completed full search with no target-feasible candidates")
    target_top = export / "target-only-top10.json" if resumed else export / "top10.json"
    if summary["top10Count"] != 0 or read_json(target_top)["candidates"]:
        raise ValueError("Fallback cannot replace an existing target top-10")
    if read_json(root / "committer-status.json").get("status") != "complete":
        raise ValueError("Wait for the original stage committer to finish")
    if not (root / "stage-commits" / "postprocess.json").exists():
        raise ValueError("Final original stage commit is missing")
    for stage, count in REQUIRED_STAGES.items():
        if len(read_json(root / "stages" / f"{stage}-results.json")) != count:
            raise ValueError(f"Required {stage} attempts are incomplete")
    if summary["mixedSplitRecords"] != 72 or summary["recentHoldoutRecords"] != 200:
        raise ValueError("Both additional split programs must be completed")
    results = []
    for stage in ("screening", "refinement", "competitors", "warm", "robustness", "postprocess"):
        results.extend(read_json(root / "stages" / f"{stage}-results.json"))
    eligible = [r for r in results if r.get("status") == "complete" and r["config"]["fold"] == "B"
                and r["config"]["seed"] == 42]
    canonical = {}
    for row in eligible:
        owner = Path(row["artifact"]).parent.name
        if row["artifact"] not in canonical or row["id"] == owner:
            canonical[row["artifact"]] = row
    return list(canonical.values()), summary


def _verify_saved_retention(root, selected, retention):
    if not retention.get("cleanupComplete") or retention["topIds"] != [r["id"] for r in selected]:
        raise ValueError("Stored fallback replay/retention is incomplete")
    for relative, digest in retention["retainedModelFiles"].items():
        if sha256_file(root / relative) != digest:
            raise ValueError("Retained fallback artifact changed")


def finalize_fallback(root, export):
    protect_favorite(export, root)
    completed = export / "fallback-summary.json"
    if completed.exists() and read_json(completed).get("status") == "complete":
        previous = read_json(export / "fallback-results.json")
        _verify_saved_retention(root, previous["candidates"], read_json(export / "retention.json"))
        write_json(export / "artifact-hashes.json", {p.name: sha256_file(p) for p in export.iterdir()
                                                     if p.is_file() and p.name != "artifact-hashes.json"})
        write_json(root / "progress.json", {"stage": "complete", "summary": read_json(export / "summary.json")})
        return read_json(completed)
    candidates, summary = finished_program_results(root, export)
    favorite = read_json(export / "favorite-validation.json")["byFold"]["B"]["metrics"]
    if any(passes_target(r["validation"][r["primaryPolicy"]]) and
           all(r["validation"][r["primaryPolicy"]][k] >= favorite[k] for k in ("precision", "recall", "f1"))
           for r in candidates):
        raise ValueError("A target-qualified improvement exists; do not use fallback")
    plan_path = root / "fallback-plan.json"
    if plan_path.exists():
        plan = read_json(plan_path)
        if plan["criteria"] != CRITERIA or plan["implementationSha256"] != sha256_file(Path(__file__)):
            raise ValueError("Frozen fallback plan implementation/criteria differ")
        selected, improvement_count = plan["candidates"], plan["substantialRecordCount"]
    else:
        retention = read_json(root / "retention.json")
        if not retention.get("allTrialWeightsPreserved") or retention["deletedFiles"] != 0:
            raise ValueError("Subtarget selection requires the original unpruned artifacts")
        selected, improvement_count = select_substantial_improvements(root, candidates, favorite)
        write_json(plan_path, {"criteria": CRITERIA, "implementationSha256": sha256_file(Path(__file__)),
                               "candidates": selected, "substantialRecordCount": improvement_count})
    if not selected:
        outcome = {"status": "no_substantial_improvement", "top10Count": 0, "criteria": CRITERIA,
                   "allTrialWeightsPreserved": True, "targetAchieved": False}
        write_json(completed, outcome)
        return outcome
    for row in selected:
        owner = Path(row["artifact"]).parent
        if sha256_file(root / owner / "selection.json") != row["selectionSha256"]:
            raise ValueError("Fallback candidate threshold changed")
    source = joblib.load(root / "dataset.joblib")
    common = source.loc[source.ApprovalFY.eq(2023)].sort_values(["approvalDate", "sourceRowIndex"])
    for row in selected:
        with np.load(root / row["predictions"]) as values:
            if (not np.array_equal(values["validationIndices"], common.sourceRowIndex.to_numpy())
                    or not np.array_equal(values["validationLabels"], common.LoanStatus.to_numpy())):
                raise ValueError("Fallback cohort differs from the fixed FY2023 favorite cohort")
    # Preserve the completed target-only outputs rather than rewriting their history.
    for name in ("summary.json", "top10.json", "top10.csv", "leaders.json", "fixed-future-diagnostics.json", "README.md"):
        target = export / f"target-only-{name}"
        if not target.exists() and (export / name).exists():
            shutil.copyfile(export / name, target)
    winner = selected[0]
    safe = next((r for r in selected if r["config"]["bundle"] != "original9_diagnostic_term_unconfirmed"
                 and r["config"]["family"] != "blend"), None)
    diagnostics = future_diagnostics(root, winner, safe, export, selected)
    plot_results(export, candidates, winner, safe, diagnostics)
    retention = read_json(root / "retention.json")
    if retention.get("cleanupComplete") and retention.get("topIds") == [r["id"] for r in selected]:
        _verify_saved_retention(root, selected, retention)
    else:
        retention = retain_top_models(root, selected, lambda path, frame: artifact_probability(root, path, frame))
    write_json(export / "retention.json", retention)
    rows = []
    for rank, candidate in enumerate(selected, 1):
        p = candidate["validation"][candidate["primaryPolicy"]]
        rows.append({"rank": rank, "id": candidate["id"], "selectionTier": "substantial_improvement_below_target",
                     "family": candidate["config"]["family"], "bundle": candidate["config"]["bundle"],
                     "validationFY": 2023, "threshold": p["threshold"], "precision": p["precision"],
                     "f1": p["f1"], "recall": p["recall"], "goalPassed": reaches_goal(p),
                     "acceptablePassed": passes_target(p), "dominatesFavorite": True,
                     "deltaPrecision": p["precision"] - favorite["precision"],
                     "deltaF1": p["f1"] - favorite["f1"], "deltaRecall": p["recall"] - favorite["recall"],
                     "primaryPolicy": candidate["primaryPolicy"], "artifact": candidate["artifact"],
                     "modelSha256": candidate["modelSha256"]})
    write_csv(export / "top10.csv", rows)
    detailed = {"favorite": favorite, "sameCohort": True, "distinctValidationDecisions": True,
                "selectionTier": "substantial_improvement_below_target", "ranking": RANKING,
                "criteria": CRITERIA, "targetAchieved": False, "candidates": [brief(r) for r in selected]}
    write_json(export / "top10.json", detailed)
    write_json(export / "fallback-results.json", detailed)
    write_json(export / "leaders.json", {"selectionTier": detailed["selectionTier"], "ranking": RANKING,
                                          "bestOverall": brief(winner), "bestWithoutTerm": brief(safe),
                                          "targetAchieved": False})
    report = ("# Существенные улучшения вне целевой зоны\n\n"
              "Цель85%/55% и допустимые границы84%/53% не достигнуты. Ниже — разные улучшения "
              "сохранённого фаворита на той же исторической FY2023-когорте при заранее выбранных порогах. "
              "Это не новый независимый тест. Ранжирование: recall, затем precision/F1.\n\n"
              "Критерий существенности: recall минимум+10 п.п., F1 минимум+5 п.п., "
              "без ухудшения precision/recall/F1. Это документированная эвристика отбора. "
              "Original9 использует срок с неподтверждённой исторической доступностью.\n\n"
              "| Место | Вариант | Порог | Precision | F1 | Recall | ΔRecall, п.п. | ΔPrecision, п.п. | ΔF1, п.п. |\n"
              "|---|---|---:|---:|---:|---:|---:|---:|---:|\n")
    for row in rows:
        report += (f"| {row['rank']} | {row['id']} | {row['threshold']:.17g} | {row['precision']:.2%} | "
                   f"{row['f1']:.2%} | {row['recall']:.2%} | {100 * row['deltaRecall']:+.2f} | "
                   f"{100 * row['deltaPrecision']:+.2f} | {100 * row['deltaF1']:+.2f} |\n")
    report += "\nВыбранные артефакты прошли replay и SHA-проверки до разрешённой очистки остальных весов. Фаворит сохранён.\n"
    (export / "fallback-report.md").write_text(report)
    readme = export / "README.md"
    if readme.exists():
        body = readme.read_text().split("## Существенные улучшения вне целевой зоны", 1)[0]
        body = body.replace("Топ-10 пуст; все веса сохранены, очистки не было.",
                            "В целевой зоне решений нет. Резервные существенные улучшения и их статус приведены ниже.")
        readme.write_text(body.rstrip() + "\n\n" + report.replace("# ", "## ", 1))
    summary.update(status="complete_with_subtarget_improvements", selectionTier=detailed["selectionTier"],
                   fallbackSelection=True, fallbackCriteria=CRITERIA, ranking=RANKING, activeTargetPassed=False,
                   aspirationalGoalPassed=False, top10Count=len(selected), bestId=winner["id"],
                   bestWithoutTermId=safe["id"] if safe else None, retentionCompleted=True,
                   substantialImprovementRecordCount=improvement_count)
    write_json(export / "summary.json", summary)
    outcome = {"status": "complete", "selectionTier": detailed["selectionTier"], "top10Count": len(selected),
               "targetAchieved": False, "criteria": CRITERIA, "candidates": rows,
               "failedRecordCount": len(summary["failedRecords"]),
               "favoriteRetained": True, "replayBeforeCleanup": True}
    write_json(completed, outcome)
    write_json(export / "artifact-hashes.json", {p.name: sha256_file(p) for p in export.iterdir()
                                                 if p.is_file() and p.name != "artifact-hashes.json"})
    write_json(root / "progress.json", {"stage": "complete", "summary": summary})
    protect_favorite(export, root)
    return outcome


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("scoring_training/runs/recall90-precision60-campaign-v1"))
    parser.add_argument("--export", type=Path, default=Path("experiments/sba-scoring-campaign-v1"))
    parser.add_argument("--apply", action="store_true", required=True,
                        help="Finalize the user-authorized post-run fallback and replay/retention")
    args = parser.parse_args()
    os.setpriority(os.PRIO_PROCESS, 0, 10)
    print(json.dumps(finalize_fallback(args.root.resolve(), args.export.resolve()), indent=2))


if __name__ == "__main__":
    main()
