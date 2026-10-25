"""Reproducible SBA tuning, refit/calibration and independent evaluation stages."""

import argparse
import importlib.metadata
import itertools
import json
import platform
import time
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from app.scoring.contracts import FEATURE_VERSION
from app.scoring.features import CATEGORICAL, FEATURES
from catboost import CatBoostClassifier
from scipy.special import expit
from sklearn.compose import ColumnTransformer
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler
from threadpoolctl import threadpool_limits

from scoring_training.data import LIMITATIONS, PREPARED_COLUMNS, sha256_file
from scoring_training.metrics import metrics, release_gates


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def load_split(prepared, name):
    manifest = read_json(prepared / "manifest.json")
    if manifest["featureVersion"] != FEATURE_VERSION or manifest["featureOrder"] != list(FEATURES):
        raise ValueError("Prepared feature schema mismatch")
    path = prepared / f"{name}.csv"
    if sha256_file(path) != manifest["files"][path.name]:
        raise ValueError("Prepared split checksum mismatch")
    frame = pd.read_csv(path, dtype={field: str for field in CATEGORICAL})
    if list(frame.columns) != list(PREPARED_COLUMNS):
        raise ValueError("Prepared column mismatch")
    spec = manifest["splits"][name]
    if (
        len(frame) != spec["rows"]
        or int(frame.LoanStatus.sum()) != spec["positives"]
        or not frame.ApprovalFY.between(*spec["years"]).all()
    ):
        raise ValueError("Prepared cohort mismatch")
    return frame


def view(frame, naics_mode, include_term=True):
    values = frame.loc[:, list(FEATURES)].copy()
    if naics_mode == "prefix2":
        values["NaicsCode"] = values.NaicsCode.str[:2]
    elif naics_mode != "full":
        raise ValueError("Unknown NAICS mode")
    if not include_term:
        values = values.drop(columns=["TermInMonths"])
    return values


def configurations():
    for mode, c in itertools.product(("full", "prefix2"), (0.01, 0.1, 1, 10)):
        yield {"family": "logistic", "naicsMode": mode, "parameters": {"C": c}}
    for mode, depth, rate, l2 in itertools.product(("full", "prefix2"), (4, 6, 8), (0.03, 0.06), (3, 10)):
        yield {
            "family": "catboost",
            "naicsMode": mode,
            "parameters": {"depth": depth, "learning_rate": rate, "l2_leaf_reg": l2},
        }


def make_model(config, include_term=True, iterations=1500):
    if config["family"] == "catboost":
        return CatBoostClassifier(
            **config["parameters"],
            loss_function="Logloss",
            iterations=iterations,
            random_seed=42,
            thread_count=4,
            task_type="CPU",
            cat_features=list(CATEGORICAL),
            verbose=False,
            allow_writing_files=False,
        )
    numerics = ["InitialInterestRate"] + (["TermInMonths"] if include_term else [])
    preprocess = ColumnTransformer(
        [
            (
                "amount",
                Pipeline(
                    [
                        ("log", FunctionTransformer(np.log1p, feature_names_out="one-to-one")),
                        ("scale", StandardScaler()),
                    ]
                ),
                ["GrossApproval"],
            ),
            ("numeric", StandardScaler(), numerics),
            ("categorical", OneHotEncoder(handle_unknown="ignore"), list(CATEGORICAL)),
        ]
    )
    return Pipeline(
        [
            ("preprocess", preprocess),
            (
                "classifier",
                LogisticRegression(**config["parameters"], solver="lbfgs", max_iter=2000, random_state=42),
            ),
        ]
    )


def fit(config, train, validation=None, include_term=True, iterations=1500):
    model = make_model(config, include_term, iterations)
    x = view(train, config["naicsMode"], include_term)
    extra = {}
    if config["family"] == "catboost" and validation is not None:
        extra = {
            "eval_set": (view(validation, config["naicsMode"], include_term), validation.LoanStatus),
            "early_stopping_rounds": 100,
            "use_best_model": True,
        }
    with warnings.catch_warnings(), threadpool_limits(limits=4):
        warnings.simplefilter("error", ConvergenceWarning)
        model.fit(x, train.LoanStatus, **extra)
    if list(model.classes_) != [0, 1]:
        raise ValueError("Positive class is not write-off=1")
    return model


def raw_scores(model, values, family):
    if family == "catboost":
        return np.asarray(model.predict(values, prediction_type="RawFormulaVal", thread_count=1))
    return np.asarray(model.decision_function(values))


def save_model(model, path, family):
    if family == "catboost":
        model.save_model(str(path))
    else:
        joblib.dump(model, path)


def choose(candidates):
    best = min(candidates, key=lambda row: row["metrics"]["logLoss"])
    simple = min(
        (row for row in candidates if row["config"]["family"] == "logistic"),
        key=lambda row: row["metrics"]["logLoss"],
    )
    return simple if simple["metrics"]["logLoss"] <= best["metrics"]["logLoss"] * 1.005 else best


def tune(prepared, output):
    output.mkdir(parents=True, exist_ok=False)
    source = read_json(prepared / "manifest.json")
    write_json(
        output / "experiment.json",
        {
            "datasetSha256": source["sourceSha256"],
            "preparedManifestSha256": sha256_file(prepared / "manifest.json"),
            "seed": 42,
            "threads": 4,
            "selection": "validation log loss; logistic within 0.5%",
            "configurations": list(configurations()),
            "limitations": LIMITATIONS,
        },
    )
    train, validation = load_split(prepared, "train"), load_split(prepared, "validation")
    candidates = []
    for index, config in enumerate(configurations()):
        start = time.perf_counter()
        model = fit(config, train, validation)
        prediction = expit(raw_scores(model, view(validation, config["naicsMode"]), config["family"]))
        suffix = "cbm" if config["family"] == "catboost" else "joblib"
        path = output / f"candidate-{index:02}.{suffix}"
        save_model(model, path, config["family"])
        result = {
            "index": index,
            "config": config,
            "metrics": metrics(validation.LoanStatus, prediction),
            "iterations": model.tree_count_ if config["family"] == "catboost" else None,
            "artifactBytes": path.stat().st_size,
            "seconds": time.perf_counter() - start,
        }
        candidates.append(result)
        write_json(output / f"candidate-{index:02}.json", result)
        print(
            json.dumps(
                {
                    "candidate": index + 1,
                    "of": 32,
                    "family": config["family"],
                    "logLoss": result["metrics"]["logLoss"],
                    "seconds": result["seconds"],
                }
            ),
            flush=True,
        )
    selected = choose(candidates)
    write_json(output / "selection.json", selected)
    # Development-only sensitivity experiment, before calibration or any test access.
    without_term = fit(selected["config"], train, validation, include_term=False)
    config = selected["config"]
    probability = expit(
        raw_scores(without_term, view(validation, config["naicsMode"], False), config["family"])
    )
    write_json(
        output / "term-diagnostic.json",
        {
            "withTerm": selected["metrics"],
            "withoutTerm": metrics(validation.LoanStatus, probability),
            "evaluationSplit": "validation",
            "directLeakageDetected": False,
            "interpretation": "Only the nine approved fields are used. Sensitivity does not establish historical term availability.",
        },
    )
    print(json.dumps({"selected": config, "validationLogLoss": selected["metrics"]["logLoss"]}), flush=True)


def freeze(prepared, experiment, package, version):
    source = read_json(prepared / "manifest.json")
    spec = read_json(experiment / "experiment.json")
    if sha256_file(prepared / "manifest.json") != spec["preparedManifestSha256"]:
        raise ValueError("Experiment dataset changed")
    selection = read_json(experiment / "selection.json")
    diagnostic = read_json(experiment / "term-diagnostic.json")
    if diagnostic["directLeakageDetected"]:
        raise ValueError("Term leakage blocks release")
    package.mkdir(parents=True, exist_ok=False)
    config = selection["config"]
    development = pd.concat(
        [load_split(prepared, "train"), load_split(prepared, "validation")], ignore_index=True
    )
    calibration = load_split(prepared, "calibration")
    model = fit(config, development, iterations=selection["iterations"] or 1500)
    raw = raw_scores(model, view(calibration, config["naicsMode"]), config["family"])
    calibrator = LogisticRegression(C=1e6, solver="lbfgs", max_iter=2000, random_state=42)
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConvergenceWarning)
        calibrator.fit(raw.reshape(-1, 1), calibration.LoanStatus)
    slope, bias = float(calibrator.coef_[0, 0]), float(calibrator.intercept_[0])
    if not np.isfinite([slope, bias]).all() or list(calibrator.classes_) != [0, 1]:
        raise ValueError("Invalid sigmoid calibrator")
    model_file = "model.cbm" if config["family"] == "catboost" else "model.joblib"
    save_model(model, package / model_file, config["family"])
    calibration_version = version + "-sigmoid-fy2017"
    write_json(
        package / "calibration.json",
        {
            "type": "sigmoid",
            "slope": slope,
            "bias": bias,
            "version": calibration_version,
            "years": source["splits"]["calibration"]["years"],
            "rows": len(calibration),
        },
    )
    values = view(development, config["naicsMode"])
    domain = {
        "numeric": {
            field: {"min": float(values[field].min()), "max": float(values[field].max())}
            for field in FEATURES
            if field not in CATEGORICAL
        },
        "categorical": {
            field: {str(key): int(count) for key, count in values[field].value_counts().items()}
            for field in CATEGORICAL
        },
        "rareThreshold": 50,
        "rows": len(development),
    }
    write_json(package / "domain.json", domain)
    write_json(
        package / "training.json",
        {
            "selection": selection,
            "termDiagnostic": diagnostic,
            "splits": source["splits"],
            "preparedManifestSha256": spec["preparedManifestSha256"],
            "sourceSha256": source["sourceSha256"],
            "trainingYears": [2010, 2016],
            "calibrationYears": [2017, 2017],
            "baselineProbability": float(load_split(prepared, "train").LoanStatus.mean()),
            "calibrationMetrics": metrics(calibration.LoanStatus, expit(slope * raw + bias)),
            "limitations": LIMITATIONS,
        },
    )
    manifest = {
        "packageFormat": "sba-package-1",
        "modelVersion": version,
        "featureVersion": FEATURE_VERSION,
        "calibrationVersion": calibration_version,
        "featureOrder": list(FEATURES),
        "positiveClass": 1,
        "modelType": config["family"],
        "naicsMode": config["naicsMode"],
        "datasetSha256": source["sourceSha256"],
        "pythonVersion": platform.python_version_tuple()[:2],
        "libraries": {
            name: importlib.metadata.version(name) for name in ("scikit-learn", "catboost", "numpy", "pandas")
        },
        "files": {file.name: sha256_file(file) for file in sorted(package.iterdir())},
        "releaseApproved": False,
        "isDemo": True,
    }
    write_json(package / "manifest.json", manifest)
    write_json(
        experiment / "frozen-before-test.json",
        {
            "manifestSha256": sha256_file(package / "manifest.json"),
            "files": manifest["files"],
            "config": config,
        },
    )
    print(json.dumps({"frozenPackage": str(package), "modelVersion": version}), flush=True)


def evaluate(prepared, experiment, package):
    from app.scoring.package import ScoringPackage

    frozen = read_json(experiment / "frozen-before-test.json")
    if sha256_file(package / "manifest.json") != frozen["manifestSha256"]:
        raise ValueError("Package changed after freeze")
    scorer = ScoringPackage(package, frozen["manifestSha256"], allow_unreleased=True)
    training = read_json(package / "training.json")
    report = {}
    for name in ("test", "transfer"):
        frame = load_split(prepared, name)
        probability = scorer.predict_frame(view(frame, scorer.manifest.naicsMode))
        baseline = metrics(frame.LoanStatus, np.full(len(frame), training["baselineProbability"]))
        slices = {}
        for field in (
            "ApprovalFY",
            "BusinessType",
            "BusinessAge",
            "RevolverStatus",
            "CollateralInd",
            "industry",
        ):
            groups = frame.NaicsCode.str[:2] if field == "industry" else frame[field]
            slices[field] = {
                str(key): metrics(frame.LoanStatus[mask], probability[mask])
                for key in groups.unique()
                if (mask := (groups == key).to_numpy()).any()
            }
        reachable = (
            frame.BusinessType.isin(["1", "2"]) & frame.BusinessAge.isin(["2", "3", "4", "5", "6", "7"])
        ).to_numpy()
        report[name] = {
            "model": metrics(frame.LoanStatus, probability),
            "baseline": baseline,
            "slices": slices,
            "backendReachable": metrics(frame.LoanStatus[reachable], probability[reachable])
            if reachable.any()
            else None,
        }
    gates = release_gates(report["test"]["model"], report["test"]["baseline"])
    gates["noDirectLeakageDetected"] = not training["termDiagnostic"]["directLeakageDetected"]
    report.update(
        releaseGates=gates,
        releaseApproved=all(gates.values()),
        limitations=LIMITATIONS,
        frozenBeforeTest=frozen,
        modelVersion=scorer.manifest.modelVersion,
    )
    write_json(package / "evaluation.json", report)
    manifest = read_json(package / "manifest.json")
    manifest["files"]["evaluation.json"] = sha256_file(package / "evaluation.json")
    manifest["releaseApproved"] = report["releaseApproved"]
    write_json(package / "manifest.json", manifest)
    # The package bytes used for inference are unchanged by the final independent evaluation.
    assert all(sha256_file(package / key) == value for key, value in frozen["files"].items())
    plot_calibration(report, package / "calibration.png")
    print(
        json.dumps(
            {
                "test": report["test"]["model"],
                "transfer": report["transfer"]["model"],
                "releaseGates": gates,
                "manifestSha256": sha256_file(package / "manifest.json"),
            }
        ),
        flush=True,
    )


def plot_calibration(report, destination):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(1, 2, figsize=(11, 4))
    for axis, name in zip(axes, ("test", "transfer"), strict=True):
        bins = report[name]["model"]["calibrationBins"]
        nonempty = [row for row in bins if row["count"]]
        axis.plot([0, 1], [0, 1], "--", color="gray")
        axis.plot([row["meanPrediction"] for row in nonempty], [row["defaultRate"] for row in nonempty], "o-")
        for row in nonempty:
            axis.annotate(str(row["count"]), (row["meanPrediction"], row["defaultRate"]), fontsize=7)
        axis.set(
            title=name,
            xlabel="Mean predicted write-off probability",
            ylabel="Observed write-off rate",
            xlim=(0, 1),
            ylim=(0, 1),
        )
        axis.grid(alpha=0.2)
    figure.tight_layout()
    figure.savefig(destination, dpi=160)
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["tune", "freeze", "evaluate"])
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--version", default="sba-scoring-v1")
    args = parser.parse_args()
    if args.stage == "tune":
        tune(args.prepared, args.experiment)
    elif args.stage == "freeze":
        freeze(args.prepared, args.experiment, args.package, args.version)
    else:
        evaluate(args.prepared, args.experiment, args.package)


if __name__ == "__main__":
    main()
