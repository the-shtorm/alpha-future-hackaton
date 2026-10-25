"""Rank distinct improved decisions and retain verified top models plus dependencies."""

import hashlib

import joblib
import numpy as np

from scoring_training.data import sha256_file
from scoring_training.thresholds import threshold_table
from scoring_training.train import write_json


def select_top_models(root, candidates, favorite, limit=10):
    def point(row):
        return row["validation"][row["primaryPolicy"]]

    def improved(row):
        values = point(row)
        return (values["precision"] >= favorite["precision"] and values["recall"] >= favorite["recall"]
                and values["f1"] > favorite["f1"]) or (
            values["f1"] > favorite["f1"] and values["recall"] >= favorite["recall"]
        )

    def rank(row):
        values = point(row)
        goal = values["precision"] >= 0.6 and values["recall"] >= 0.9
        safe = row["config"]["bundle"] != "original9_diagnostic_term_unconfirmed"
        calibrated = row["config"].get("calibrationMethod") != "none"
        return (int(goal), values["f1"], values["recall"], values["precision"], int(safe), int(calibrated))

    qualifying = [row for row in candidates if improved(row)]
    # If nothing improved, retain the best measured alternatives without labeling
    # them improvements. The final report must expose this case explicitly.
    pool = qualifying or candidates
    selected, masks = [], set()
    for row in sorted(pool, key=rank, reverse=True):
        data = np.load(root / row["predictions"])
        flagged = data["validationProbability"] >= row["selectionPoint"]["threshold"]
        digest = hashlib.sha256(data["validationIndices"].tobytes() + np.packbits(flagged).tobytes()).hexdigest()
        if digest in masks:
            continue
        masks.add(digest)
        selected.append(row)
        if len(selected) == limit:
            break
    return selected, len(qualifying)


def _model_path(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to((root / "trials").resolve()) or path.name != "model.joblib":
        raise ValueError("Retention path is outside research model artifacts")
    return path


def model_dependencies(root, relative, retained=None):
    retained = set() if retained is None else retained
    path = _model_path(root, relative)
    if path in retained:
        return retained
    retained.add(path)
    artifact = joblib.load(path)
    if artifact.get("kind") == "blend":
        model_dependencies(root, artifact["left"], retained)
        model_dependencies(root, artifact["right"], retained)
    elif artifact.get("kind") == "recalibrated":
        model_dependencies(root, artifact["base"], retained)
    return retained


def retain_top_models(root, selected, predict_probability):
    """User-authorized cleanup runs only after exact top-model prediction replay.

    Favorite lives outside trials and is never a cleanup candidate. Keep all
    aggregate metrics/configurations; remove other heavy trial weights/predictions.
    """
    if not selected:
        raise ValueError("No verified candidates; cleanup is forbidden")
    frame = joblib.load(root / "dataset.joblib").set_index("sourceRowIndex", drop=False)
    keep, selected_predictions, verification = set(), set(), []
    for row in selected:
        path = _model_path(root, row["artifact"])
        if sha256_file(path) != row["modelSha256"]:
            raise ValueError("Top-model artifact checksum mismatch")
        data_path = (root / row["predictions"]).resolve()
        if not data_path.is_relative_to((root / "trials").resolve()):
            raise ValueError("Prediction path outside research trials")
        data = np.load(data_path)
        cohort = frame.loc[data["validationIndices"]]
        if not np.array_equal(cohort.LoanStatus, data["validationLabels"]):
            raise ValueError("Top-model replay cohort mismatch")
        probability = predict_probability(row["artifact"], cohort)
        if not np.allclose(probability, data["validationProbability"], rtol=1e-10, atol=1e-12):
            raise ValueError("Top-model prediction replay mismatch")
        actual = threshold_table(cohort.LoanStatus, probability, [row["selectionPoint"]["threshold"]])[0]
        expected = row["validation"][row["primaryPolicy"]]
        if any(actual[key] != expected[key] for key in ("tp", "fp", "fn", "tn")):
            raise ValueError("Top-model decision replay mismatch")
        keep.update(model_dependencies(root, row["artifact"]))
        selected_predictions.add(data_path)
        verification.append({"id": row["id"], "modelSha256": row["modelSha256"],
                             "validationReplayPassed": True})
    delete = []
    for directory in (root / "trials").iterdir():
        for name in ("model.joblib", "predictions.npz"):
            path = directory / name
            if not path.exists():
                continue
            resolved = path.resolve()
            if not resolved.is_relative_to((root / "trials").resolve()):
                raise ValueError("Cleanup encountered an external symlink")
            if resolved not in keep and resolved not in selected_predictions:
                delete.append(resolved)
    deleted_bytes = sum(path.stat().st_size for path in delete)
    manifest = {
        "topIds": [row["id"] for row in selected], "verification": verification,
        "retainedModelFiles": {str(path.relative_to(root.resolve())): sha256_file(path) for path in sorted(keep)},
        "favoriteUntouched": True, "aggregateMetricsAndConfigsRetained": True,
        "plannedDeletedFiles": len(delete), "plannedFreedBytes": deleted_bytes, "cleanupComplete": False,
    }
    write_json(root / "retention.json", manifest)
    for path in delete:
        path.unlink()
    manifest["cleanupComplete"] = True
    manifest["deletedFiles"] = len(delete)
    manifest["freedBytes"] = deleted_bytes
    write_json(root / "retention.json", manifest)
    return manifest
