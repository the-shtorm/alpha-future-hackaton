"""One restartable research fit: calibration, exact thresholds, then fixed validation."""

import hashlib
import json
import time
import traceback
import warnings
from pathlib import Path

import joblib
import numpy as np
from catboost import CatBoostClassifier
from scipy.special import logit
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from threadpoolctl import threadpool_limits

from scoring_training.business_thresholds import business_operating_points
from scoring_training.campaign_data import FeatureBuilder, categorical_columns, cohort_frames, time_weights
from scoring_training.data import sha256_file
from scoring_training.thresholds import threshold_table
from scoring_training.train import write_json

_FRAME = None
_ROOT = None


def initialize_worker(cache, root):
    global _FRAME, _ROOT
    _FRAME, _ROOT = joblib.load(cache), Path(root)


def signature(config):
    normalized = {key: value for key, value in config.items() if key not in ("id", "stage", "parent")}
    # No source data precedes FY2010: all-history and an overly long window are identical.
    from scoring_training.campaign_data import FOLDS

    last = FOLDS[config["fold"]]["fitThroughFY"]
    window = config.get("window")
    normalized["effectiveStartFY"] = max(2010, last - window + 1) if window else 2010
    normalized.pop("window", None)
    return hashlib.sha256(json.dumps(normalized, sort_keys=True).encode()).hexdigest()


def primary_point(selection):
    for name in ("optimal", "bestPrecisionAtRecallFloor", "bestRecallAtPrecisionFloor", "unconstrainedMaximumF1"):
        if selection.get(name) is not None:
            return name, selection[name]
    raise ValueError("No operating point")


def evaluate_points(selection, labels, probability):
    policies = {name: value for name, value in selection.items()
                if name in ("optimal", "bestRecallAtPrecisionFloor", "bestPrecisionAtRecallFloor",
                            "unconstrainedMaximumF1") and value is not None}
    table = {row["threshold"]: row for row in threshold_table(
        labels, probability, [row["threshold"] for row in policies.values()]
    )}
    return {name: dict(table[row["threshold"]]) for name, row in policies.items()}


def result_rank(result):
    if result.get("status") != "complete":
        return (-1,)
    row = result["validation"][result["primaryPolicy"]]
    passed = row["precision"] >= 0.6 and row["recall"] >= 0.9
    if passed:
        return (1, row["f1"], row["recall"], row["precision"])
    return (0, min(row["precision"] / 0.6, row["recall"] / 0.9), row["f1"],
            row["recall"], row["precision"])


def _class_weights(labels, sample_weights, mode):
    if isinstance(mode, str):
        ratio = sample_weights[labels == 0].sum() / sample_weights[labels == 1].sum()
        return float(np.sqrt(ratio) if mode == "SqrtBalanced" else ratio)
    return float(mode)


def _fit_model(config, x, y, early_x, early_y, weights, categorical, root):
    family = config["family"]
    parameters = dict(config.get("parameters", {}))
    seed = config.get("seed", 42)
    if family == "catboost":
        settings = {
            "depth": 6, "learning_rate": 0.06, "l2_leaf_reg": 10, "iterations": 3000,
            "loss_function": "Logloss", "eval_metric": "PRAUC:type=Classic;use_weights=False",
            "random_seed": seed, "thread_count": 2, "task_type": "CPU", "verbose": False,
            "allow_writing_files": False, **parameters,
        }
        model = CatBoostClassifier(**settings, cat_features=categorical)
        extra = {}
        if config.get("initArtifact"):
            initial = joblib.load(root / config["initArtifact"])
            if list(initial["builder"].transform(initial["featureExample"]).columns) != list(x.columns):
                raise ValueError("Warm-start feature schema mismatch")
            extra["init_model"] = initial["model"]
        model.fit(x, y, sample_weight=weights, eval_set=(early_x, early_y),
                  early_stopping_rounds=150, use_best_model=True, **extra)
        return model, None
    if family in ("lightgbm", "xgboost"):
        categories = {name: sorted(x[name].unique().tolist()) for name in categorical}

        def category_view(frame):
            frame = frame.copy()
            for name, values in categories.items():
                frame[name] = frame[name].astype(__import__("pandas").CategoricalDtype(categories=values))
            return frame

        train_x, validation_x = category_view(x), category_view(early_x)
        if family == "lightgbm":
            from lightgbm import LGBMClassifier, early_stopping, log_evaluation

            model = LGBMClassifier(n_estimators=3000, n_jobs=2, random_state=seed, verbosity=-1, **parameters)
            model.fit(train_x, y, sample_weight=weights, eval_set=[(validation_x, early_y)],
                      eval_metric="average_precision", callbacks=[early_stopping(150, first_metric_only=True,
                                                                                 verbose=False), log_evaluation(0)])
        else:
            from xgboost import XGBClassifier

            model = XGBClassifier(n_estimators=3000, n_jobs=2, random_state=seed, tree_method="hist",
                                  enable_categorical=True, eval_metric="aucpr", early_stopping_rounds=150,
                                  **parameters)
            model.fit(train_x, y, sample_weight=weights, eval_set=[(validation_x, early_y)], verbose=False)
        return model, categories
    numeric = [name for name in x if name not in categorical]
    prep = ColumnTransformer([
        ("numeric", StandardScaler(), numeric),
        ("categorical", OneHotEncoder(handle_unknown="infrequent_if_exist", min_frequency=50), categorical),
    ])
    if family == "logistic":
        estimator = LogisticRegression(max_iter=2000, random_state=seed, **parameters)
    elif family == "randomForest":
        estimator = RandomForestClassifier(n_estimators=500, n_jobs=2, random_state=seed, **parameters)
    else:
        raise ValueError("Unknown candidate family")
    model = Pipeline([("features", prep), ("model", estimator)])
    model.fit(x, y, model__sample_weight=weights)
    return model, None


def raw_prediction(model, values, family, categories):
    if family == "catboost":
        return np.asarray(model.predict(values, prediction_type="RawFormulaVal", thread_count=2))
    if categories:
        import pandas as pd

        values = values.copy()
        for name, known in categories.items():
            values[name] = values[name].astype(pd.CategoricalDtype(categories=known))
    return logit(np.clip(model.predict_proba(values)[:, 1], 1e-12, 1 - 1e-12))


def run_trial(config):
    """Every worker has private artifacts; failures remain visible and restartable."""
    started = time.monotonic()
    directory = _ROOT / "trials" / config["id"]
    directory.mkdir(parents=True, exist_ok=True)
    result_path = directory / "result.json"
    if result_path.exists():
        previous = json.loads(result_path.read_text())
        if previous.get("status") == "complete" and previous["config"] == config:
            return previous
    write_json(directory / "config.json", config)
    try:
        cohorts, audit = cohort_frames(_FRAME, config["fold"], config.get("window"))
        training = cohorts["fit"]
        if config.get("replayFraction") is not None:
            last = int(training.ApprovalFY.max())
            recent = training.ApprovalFY.ge(last - config["recentWindow"] + 1)
            old = training.loc[~recent].sample(frac=config["replayFraction"], random_state=config["seed"])
            training = __import__("pandas").concat([training.loc[recent], old]).sort_values(
                ["approvalDate", "sourceRowIndex"]
            )
        builder = FeatureBuilder(config["bundle"])
        x = builder.fit_transform(training)
        weights = time_weights(training, audit["simulationCutoff"], config.get("halfLife"))
        y = training.LoanStatus.to_numpy()
        multiplier = _class_weights(y, weights, config.get("balance", 1))
        weights = weights * np.where(y == 1, multiplier, 1.0)
        weights /= weights.mean()
        with warnings.catch_warnings(record=True) as captured, threadpool_limits(limits=2):
            model, categories = _fit_model(
                config, x, y, builder.transform(cohorts["early"]), cohorts["early"].LoanStatus,
                weights, categorical_columns(x), _ROOT,
            )
        if list(model.classes_) != [0, 1]:
            raise ValueError("Model class ordering differs from write-off=1")
        cal_raw = raw_prediction(model, builder.transform(cohorts["calibration"]), config["family"], categories)
        calibrator = LogisticRegression(C=1e6, max_iter=2000).fit(
            cal_raw.reshape(-1, 1), cohorts["calibration"].LoanStatus
        )
        threshold_raw = raw_prediction(model, builder.transform(cohorts["threshold"]), config["family"], categories)
        probability = calibrator.predict_proba(threshold_raw.reshape(-1, 1))[:, 1]
        selection = business_operating_points(cohorts["threshold"].LoanStatus, probability)
        # Freeze complete selection BEFORE accessing validation labels for scoring.
        write_json(directory / "selection.json", selection)
        selection_sha = sha256_file(directory / "selection.json")
        policy, point = primary_point(selection)
        validation = cohorts["validation"]
        validation_raw = raw_prediction(model, builder.transform(validation), config["family"], categories)
        validation_probability = calibrator.predict_proba(validation_raw.reshape(-1, 1))[:, 1]
        evaluation = evaluate_points(selection, validation.LoanStatus, validation_probability)
        artifact = {
            "model": model, "builder": builder, "categories": categories, "calibrator": calibrator,
            "config": config, "featureExample": training.iloc[:1],
        }
        joblib.dump(artifact, directory / "model.joblib")
        np.savez_compressed(
            directory / "predictions.npz", calibrationRaw=cal_raw,
            calibrationLabels=cohorts["calibration"].LoanStatus.to_numpy(),
            thresholdRaw=threshold_raw, thresholdProbability=probability,
            thresholdLabels=cohorts["threshold"].LoanStatus.to_numpy(),
            thresholdIndices=cohorts["threshold"].sourceRowIndex.to_numpy(),
            validationRaw=validation_raw, validationProbability=validation_probability,
            validationLabels=validation.LoanStatus.to_numpy(), validationIndices=validation.sourceRowIndex.to_numpy(),
        )
        row = evaluation[policy]
        result = {
            "id": config["id"], "status": "complete", "config": config, "signature": signature(config),
            "audit": audit, "resolvedPositiveWeight": multiplier,
            "actualTrainingRows": len(training), "treeCount": int(getattr(model, "tree_count_", 0)),
            "selection": selection, "primaryPolicy": policy, "selectionPoint": point,
            "selectionSha256": selection_sha, "validation": evaluation,
            "validationTargetPassed": row["precision"] >= 0.6 and row["recall"] >= 0.9,
            "artifact": str((directory / "model.joblib").relative_to(_ROOT)),
            "modelSha256": sha256_file(directory / "model.joblib"),
            "predictions": str((directory / "predictions.npz").relative_to(_ROOT)),
            "fitSeconds": time.monotonic() - started,
            "implementationSha256": {name: sha256_file(Path(__file__).with_name(name))
                                     for name in ("campaign_fit.py", "campaign_data.py", "business_thresholds.py",
                                                  "thresholds.py")},
            "warnings": sorted({str(item.message)[:250] for item in captured}),
            "deployable": False,
        }
        if sha256_file(directory / "selection.json") != selection_sha:
            raise ValueError("Selection changed during evaluation")
    except Exception as error:
        result = {"id": config["id"], "status": "failed", "config": config,
                  "error": f"{type(error).__name__}: {error}", "traceback": traceback.format_exc(),
                  "fitSeconds": time.monotonic() - started}
    write_json(result_path, result)
    return result
