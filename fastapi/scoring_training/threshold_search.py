"""Search frozen SBA model thresholds on FY2017, then evaluate fixed later-cohort policies."""

import argparse
import csv
from pathlib import Path

import numpy as np
from app.scoring.package import ScoringPackage

from scoring_training.data import sha256_file
from scoring_training.thresholds import select_policies, threshold_table
from scoring_training.train import load_split, read_json, view, write_json

BASELINES = {"baseline_0.15": 0.15, "baseline_0.35": 0.35, "baseline_0.5": 0.5}
LIMITATIONS = [
    "FY2017 selected thresholds and also fitted the existing sigmoid calibrator; development metrics are optimistic.",
    "Later cohorts have been evaluated historically; this is an existing retrospective benchmark, not fresh external validation.",
    "Development recall floors do not guarantee future recall; no later-cohort threshold retuning is performed.",
    "The chosen recall floor is an experimental assumption, not an agreed business constraint.",
    "F2 gives recall more weight; F1 itself weights precision and recall equally.",
    "A binary flag threshold does not reproduce the Java multistep affordability and alternative-offer policy.",
    "A review flag is not an automatic loan rejection; workload is measured by flaggedShare and false positives.",
]


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def evaluate_policies(labels, probability, cutoffs):
    table = {row["threshold"]: row for row in threshold_table(labels, probability, list(cutoffs.values()))}
    return {name: dict(table[cutoff]) for name, cutoff in cutoffs.items()}


def evaluate_cohort(frame, probability, cutoffs):
    reachable = (
        frame.BusinessType.isin(["1", "2"]) & frame.BusinessAge.isin(["2", "3", "4", "5", "6", "7"])
    ).to_numpy()
    return {
        "rows": len(frame),
        "positives": int(frame.LoanStatus.sum()),
        "policies": evaluate_policies(frame.LoanStatus, probability, cutoffs),
        "byYear": {
            str(year): evaluate_policies(frame.LoanStatus[mask], probability[mask], cutoffs)
            for year in sorted(frame.ApprovalFY.unique())
            if (mask := (frame.ApprovalFY == year).to_numpy()).any()
        },
        "backendReachable": evaluate_policies(frame.LoanStatus[reachable], probability[reachable], cutoffs)
        if reachable.any()
        else None,
    }


def search(prepared, package, lock, output, *, recommended_recall=0.95):
    if not 0 < recommended_recall <= 1:
        raise ValueError("Recall floor must be in (0, 1]")
    scorer = ScoringPackage(package, read_json(lock)["manifestSha256"])
    training, source = read_json(package / "training.json"), read_json(prepared / "manifest.json")
    if (
        source["sourceSha256"] != scorer.manifest.datasetSha256
        or sha256_file(prepared / "manifest.json") != training["preparedManifestSha256"]
    ):
        raise ValueError("Prepared data does not match the frozen model provenance")
    output.mkdir(parents=True, exist_ok=False)
    development = load_split(prepared, "calibration")
    probability = scorer.predict_frame(view(development, scorer.manifest.naicsMode))
    table = threshold_table(development.LoanStatus, probability)
    policies = select_policies(table, recommended_recall)
    cutoffs = {**BASELINES, **{name: row["threshold"] for name, row in policies.items()}}
    selection = {
        "schemaVersion": "sba-threshold-experiment-1",
        "modelVersion": scorer.manifest.modelVersion,
        "manifestSha256": sha256_file(package / "manifest.json"),
        "preparedManifestSha256": sha256_file(prepared / "manifest.json"),
        "sourceSha256": source["sourceSha256"],
        "implementationSha256": {
            name: sha256_file(Path(__file__).with_name(name))
            for name in ("thresholds.py", "threshold_search.py")
        },
        "selectionSplit": "calibration",
        "selectionYears": source["splits"]["calibration"]["years"],
        "comparison": "probability >= threshold; write-off is positive class 1",
        "search": "all distinct calibrated probabilities plus boundaries 0 and 1",
        "candidateCount": len(table),
        "tieBreak": "maximum recall, then precision, then threshold",
        "recommendedObjective": {"metric": "f1", "minRecall": recommended_recall},
        "nearBestF1AbsoluteTolerance": 0.01,
        "policies": policies,
        "baselineThresholds": BASELINES,
        "allThresholds": cutoffs,
        "limitations": [*source["limitations"], *LIMITATIONS],
    }
    # Persist selection BEFORE loading any later cohort. Reload the persisted
    # values so evaluation cannot implicitly re-optimize policies on holdouts.
    write_json(output / "selection.json", selection)
    frozen_sha256 = sha256_file(output / "selection.json")
    cutoffs = read_json(output / "selection.json")["allThresholds"]
    write_csv(output / "development-exact-curve.csv", table)
    grid = threshold_table(development.LoanStatus, probability, np.linspace(0, 1, 201))
    write_csv(output / "development-grid.csv", grid)
    evaluation = {"calibration": evaluate_cohort(development, probability, cutoffs)}
    for name in ("test", "transfer"):
        cohort = load_split(prepared, name)
        prediction = scorer.predict_frame(view(cohort, scorer.manifest.naicsMode))
        evaluation[name] = evaluate_cohort(cohort, prediction, cutoffs)
    if sha256_file(output / "selection.json") != frozen_sha256:
        raise ValueError("Threshold selection changed during evaluation")
    results = {
        "selectionSha256": frozen_sha256,
        "modelVersion": scorer.manifest.modelVersion,
        "cohorts": evaluation,
        "runtimePolicyChanged": False,
    }
    write_json(output / "evaluation.json", results)
    write_csv(
        output / "comparison.csv",
        [{"split": split, "policy": name, **row}
         for split, cohort in evaluation.items() for name, row in cohort["policies"].items()],
    )
    return results


def plot_results(output):
    """Static scientific figure; holdout points are fixed policies, not tuned curves."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd

    selection = read_json(output / "selection.json")
    evaluation = read_json(output / "evaluation.json")["cohorts"]
    grid = pd.read_csv(output / "development-grid.csv")
    figure, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    for metric in ("precision", "recall", "f1", "f2"):
        axes[0].plot(grid.threshold, grid[metric], label=metric.upper())
    for name, color in (("maximum_f1", "gray"), ("recommended", "black")):
        axes[0].axvline(selection["allThresholds"][name], color=color, linestyle="--", alpha=0.6)
    axes[0].set(title="FY2017 development: exact search, sampled curve", xlabel="Threshold", ylabel="Metric")
    names = ["baseline_0.35", "baseline_0.15", "maximum_f1", "maximum_f2", "recommended"]
    x = np.arange(len(names))
    for split, marker in (("calibration", "o"), ("test", "s"), ("transfer", "^")):
        rows = evaluation[split]["policies"]
        axes[1].plot(x, [rows[name]["recall"] for name in names], marker=marker, label=split)
    axes[1].axhline(selection["recommendedObjective"]["minRecall"], linestyle="--", color="gray")
    axes[1].set(
        title="Recall of policies frozen on FY2017", ylabel="Recall", xticks=x,
        xticklabels=["p >= .35", "p >= .15", "max F1", "max F2", "F1 + recall floor"],
    )
    for axis in axes:
        axis.set_ylim(0, 1.02)
        axis.grid(alpha=0.2)
        axis.legend()
    figure.tight_layout()
    figure.savefig(output / "threshold-tradeoffs.png", dpi=170)
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--lock", type=Path, default=Path("config/scoring-model.lock.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--recommended-recall", type=float, default=0.95)
    args = parser.parse_args()
    results = search(args.prepared, args.package, args.lock, args.output,
                     recommended_recall=args.recommended_recall)
    plot_results(args.output)
    for split, cohort in results["cohorts"].items():
        row = cohort["policies"]["recommended"]
        print(f"{split}: threshold={row['threshold']:.12g}, F1={row['f1']:.6f}, "
              f"recall={row['recall']:.6f}, precision={row['precision']:.6f}, "
              f"TP={row['tp']}, FN={row['fn']}, FP={row['fp']}")
    print(f"Saved immutable selection and evaluation to {args.output}")


if __name__ == "__main__":
    main()
