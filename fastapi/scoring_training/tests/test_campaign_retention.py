"""Final rankings cannot duplicate decisions or prune unreplayed/favorite models."""

import joblib
import numpy as np
import pandas as pd
import pytest
from scoring_training.campaign_retention import model_dependencies, retain_top_models, select_top_models
from scoring_training.data import sha256_file
from scoring_training.thresholds import threshold_table

LABELS = np.array([1, 0, 1, 0, 1, 0])


def candidate(root, name, probability, artifact=None):
    path = root / "trials" / name
    path.mkdir(parents=True)
    artifact = {"probability": probability} if artifact is None else artifact
    joblib.dump(artifact, path / "model.joblib")
    np.savez_compressed(path / "predictions.npz", validationIndices=np.arange(6), validationLabels=LABELS,
                        validationProbability=probability)
    point = threshold_table(LABELS, probability, [0.5])[0]
    return {"id": name, "config": {"bundle": "safe8_without_term"}, "primaryPolicy": "optimal",
            "selectionPoint": point, "validation": {"optimal": point},
            "artifact": f"trials/{name}/model.joblib", "modelSha256": sha256_file(path / "model.joblib"),
            "predictions": f"trials/{name}/predictions.npz"}


def test_top_models_prioritize_goals_and_deduplicate_identical_binary_decisions(tmp_path):
    lower = candidate(tmp_path, "lower", np.array([0.9, 0.1, 0.8, 0.1, 0.1, 0.1]))
    goal = candidate(tmp_path, "goal", np.array([0.9, 0.1, 0.8, 0.1, 0.8, 0.1]))
    duplicate = candidate(tmp_path, "duplicate", np.array([0.99, 0.01, 0.9, 0.01, 0.9, 0.01]))
    duplicate["config"]["calibrationMethod"] = "none"
    chosen, improvements = select_top_models(tmp_path, [lower, goal, duplicate],
                                             {"precision": 0.4, "recall": 0.4, "f1": 0.4})
    assert improvements == 3
    assert [row["id"] for row in chosen] == ["goal", "lower"]


def test_cleanup_keeps_favorite_top_model_dependencies_and_all_verified_predictions(tmp_path):
    probability = np.array([0.9, 0.1, 0.8, 0.1, 0.8, 0.1])
    left = candidate(tmp_path, "left", probability)
    right = candidate(tmp_path, "right", probability)
    top = candidate(tmp_path, "top", probability, {"kind": "blend", "left": left["artifact"],
                                                 "right": right["artifact"], "probability": probability})
    trash = candidate(tmp_path, "trash", probability)
    joblib.dump(pd.DataFrame({"sourceRowIndex": np.arange(6), "LoanStatus": LABELS}), tmp_path / "dataset.joblib")
    favorite = tmp_path / "favorite-package" / "model.cbm"
    favorite.parent.mkdir()
    favorite.write_bytes(b"favorite bytes remain identical")
    manifest = retain_top_models(tmp_path, [top], lambda path, frame: joblib.load(tmp_path / path)["probability"])
    assert manifest["cleanupComplete"] is True
    assert len(manifest["retainedModelFiles"]) == 3
    assert (tmp_path / top["artifact"]).exists()
    assert (tmp_path / left["artifact"]).exists()
    assert (tmp_path / right["artifact"]).exists()
    assert (tmp_path / top["predictions"]).exists()
    assert not (tmp_path / trash["artifact"]).exists()
    assert not (tmp_path / trash["predictions"]).exists()
    assert favorite.read_bytes() == b"favorite bytes remain identical"


def test_failed_replay_forbids_any_cleanup(tmp_path):
    probability = np.array([0.9, 0.1, 0.8, 0.1, 0.8, 0.1])
    top = candidate(tmp_path, "top", probability)
    trash = candidate(tmp_path, "trash", probability)
    joblib.dump(pd.DataFrame({"sourceRowIndex": np.arange(6), "LoanStatus": LABELS}), tmp_path / "dataset.joblib")
    with pytest.raises(ValueError, match="replay mismatch"):
        retain_top_models(tmp_path, [top], lambda path, frame: np.zeros(6))
    assert (tmp_path / trash["artifact"]).exists()


def test_dependency_retention_cannot_enter_favorite_or_external_directories(tmp_path):
    with pytest.raises(ValueError, match="outside"):
        model_dependencies(tmp_path, "favorite-package/model.joblib")
