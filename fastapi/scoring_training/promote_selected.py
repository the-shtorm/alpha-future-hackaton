"""Export the user's selected original9 CatBoost without fitting or threshold search."""

import argparse
import importlib.metadata
import platform
from pathlib import Path

import joblib
import numpy as np
from app.scoring.contracts import FEATURE_VERSION
from app.scoring.features import CATEGORICAL, FEATURES, NUMERIC
from app.scoring.package import ScoringPackage

from scoring_training.campaign_mixed import mixed_cohorts
from scoring_training.campaign_postprocess import metrics_for_frame
from scoring_training.data import sha256_file
from scoring_training.train import read_json, write_json


def export_selected(selection_path, run, output, version):
    selected = read_json(selection_path)
    snapshot = Path(selected["localSnapshot"]).relative_to("fastapi")
    for name, expected in selected["snapshotFiles"].items():
        if sha256_file(snapshot / name) != expected:
            raise ValueError("Selected source snapshot checksum mismatch")
    result = read_json(snapshot / "result.json")
    config = result["config"]
    threshold = result["selectionPoint"]["threshold"]
    if (
        selected["selectedBy"] != "user"
        or result["id"] != selected["id"]
        or threshold != selected["threshold"]
        or config["family"] != "catboost"
        or config["bundle"] != "original9_diagnostic_term_unconfirmed"
        or config["splitStrategy"] != "random_years"
        or config["window"] is not None
    ):
        raise ValueError("Unsupported or changed selected model")
    if sha256_file(snapshot / "selection.json") != result["selectionSha256"]:
        raise ValueError("Frozen threshold selection changed")
    protocol = read_json(selection_path.parent / "protocol.json")
    if sha256_file(run / "dataset.joblib") != protocol["cacheSha256"]:
        raise ValueError("Source dataset cache changed")
    source = joblib.load(run / "dataset.joblib")
    cohorts, audit = mixed_cohorts(source, config["splitStrategy"], config["splitSeed"])
    if audit != result["audit"] or len(cohorts["fit"]) != result["actualTrainingRows"]:
        raise ValueError("Selected split provenance changed")
    saved = joblib.load(snapshot / "model.joblib")
    if saved["config"] != config or list(saved["calibrator"].classes_) != [0, 1]:
        raise ValueError("Selected model/calibrator mismatch")
    fit = saved["builder"].transform(cohorts["fit"])
    if list(fit) != list(FEATURES) or not fit.equals(cohorts["fit"].loc[:, FEATURES]):
        raise ValueError("Native export cannot reproduce selected feature builder")
    output.mkdir(parents=True, exist_ok=False)
    saved["model"].save_model(str(output / "model.cbm"))
    years = audit["calibration"]["approvalFiscalYears"]
    calibration_years = [min(years), max(years)]
    calibration_version = version + "-sigmoid-fy" + str(years[0])
    write_json(output / "calibration.json", {
        "type": "sigmoid", "slope": float(saved["calibrator"].coef_[0, 0]),
        "bias": float(saved["calibrator"].intercept_[0]), "version": calibration_version,
        "years": calibration_years, "rows": len(cohorts["calibration"]),
    })
    write_json(output / "domain.json", {
        "numeric": {name: {"min": float(fit[name].min()), "max": float(fit[name].max())}
                    for name in NUMERIC},
        "categorical": {name: {str(k): int(v) for k, v in fit[name].value_counts().items()}
                        for name in CATEGORICAL},
        "rareThreshold": 50, "rows": len(fit),
    })
    write_json(output / "training.json", {
        "sourceTrial": result["id"], "sourceArtifactSha256": result["modelSha256"],
        "sourceSelectionSha256": result["selectionSha256"], "sourceSha256": protocol["sourceSha256"],
        "config": config, "audit": audit, "calibrationYears": calibration_years,
        "trainingFiscalYears": audit["fit"]["approvalFiscalYears"],
        "baselineProbability": float(cohorts["fit"].LoanStatus.mean()),
        "operatingPoint": {"policy": result["primaryPolicy"], "threshold": threshold,
                           "selectedOn": "historical FY2015 threshold cohort, before FY2023 evaluation"},
        "limitations": selected["limitations"][:2] + [
            "Selected on previously inspected historical results; not an independent prospective test.",
            "SBA completed-loan demo; quality deteriorates on later fiscal years.",
            "This operating point does not replace the Java financial decision policy.",
        ],
    })
    manifest = {
        "packageFormat": "sba-package-1", "modelVersion": version, "featureVersion": FEATURE_VERSION,
        "calibrationVersion": calibration_version, "calibrationYears": calibration_years,
        "operatingThreshold": threshold, "featureOrder": list(FEATURES), "positiveClass": 1,
        "modelType": "catboost", "naicsMode": "full", "datasetSha256": protocol["sourceSha256"],
        "pythonVersion": list(platform.python_version_tuple()[:2]),
        "libraries": {name: importlib.metadata.version(name)
                      for name in ("scikit-learn", "catboost", "numpy", "pandas")},
        "files": {p.name: sha256_file(p) for p in sorted(output.iterdir())},
        "releaseApproved": False, "isDemo": True,
    }
    write_json(output / "manifest.json", manifest)
    scorer = ScoringPackage(output, sha256_file(output / "manifest.json"), allow_unreleased=True)
    # Compare native serving + JSON sigmoid to the original pickled pipeline.
    cohort = cohorts["validation"]
    values = saved["builder"].transform(cohort)
    raw = saved["model"].predict(values, prediction_type="RawFormulaVal", thread_count=1)
    expected_probability = saved["calibrator"].predict_proba(np.asarray(raw).reshape(-1, 1))[:, 1]
    probability = scorer.predict_frame(values)
    if not np.allclose(probability, expected_probability, rtol=1e-10, atol=1e-12):
        raise ValueError("Native probability replay differs")
    with np.load(run / result["predictions"]) as stored:
        if (not np.array_equal(cohort.sourceRowIndex, stored["validationIndices"])
                or not np.array_equal(cohort.LoanStatus, stored["validationLabels"])
                or not np.allclose(probability, stored["validationProbability"], rtol=1e-10, atol=1e-12)):
            raise ValueError("Frozen validation prediction archive differs")
    actual = metrics_for_frame(cohort, probability, threshold)
    expected = result["validation"][result["primaryPolicy"]]
    if any(actual[k] != expected[k] for k in ("tp", "fp", "fn", "tn", "precision", "recall", "f1")):
        raise ValueError("Native operating point differs")
    baseline = selected["originalFavorite"]["metrics"]
    dominates = all(actual[k] > baseline[k] for k in ("precision", "recall", "f1"))
    if not dominates:
        raise ValueError("Selected model no longer improves favorite")
    by_year = {"2023": actual}
    for year in (2024, 2025, 2026):
        group = source.loc[source.ApprovalFY.eq(year)]
        by_year[str(year)] = metrics_for_frame(group, scorer.predict_frame(saved["builder"].transform(group)),
                                             threshold)
    evaluation = {
        "modelVersion": version, "sourceTrial": result["id"], "releaseApproved": True,
        "approvalScope": "User-selected demonstration model; no production banking approval",
        "releaseGates": {"sourceAndSplitChecksumsMatch": True, "nativeProbabilityReplayPassed": True,
                         "frozenConfusionCountsMatch": True, "improvesFavoriteOnFY2023": dominates,
                         "userSelectedForDemo": True},
        "historicalValidation": actual, "historicalByYear": by_year,
        "historicalRandomTest": result["historicalRandomTest"]["policies"][result["primaryPolicy"]],
        "deltaVsFavorite": {k: actual[k] - baseline[k] for k in ("precision", "recall", "f1")},
        "goal85Recall55PrecisionReached": False, "tolerance84Recall53PrecisionReached": False,
        "thresholdChanged": False, "retrained": False, "freshIndependentTest": False,
        "probabilityMaxAbsoluteDifference": float(np.max(np.abs(probability - expected_probability))),
    }
    write_json(output / "evaluation.json", evaluation)
    manifest["releaseApproved"] = True
    manifest["files"]["evaluation.json"] = sha256_file(output / "evaluation.json")
    write_json(output / "manifest.json", manifest)
    final = ScoringPackage(output, sha256_file(output / "manifest.json"))
    assert np.array_equal(final.predict_frame(values), probability)
    return {"modelVersion": version, "manifestSha256": sha256_file(output / "manifest.json"),
            "historicalValidation": actual, "nativeReplayPassed": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path,
                        default=Path("experiments/sba-scoring-campaign-v1/selected-model.json"))
    parser.add_argument("--run", type=Path,
                        default=Path("scoring_training/runs/recall90-precision60-campaign-v1"))
    parser.add_argument("--output", type=Path, default=Path("models/sba-scoring-v2"))
    parser.add_argument("--version", default="sba-scoring-v2")
    args = parser.parse_args()
    print(export_selected(args.selection, args.run, args.output, args.version))


if __name__ == "__main__":
    main()
