"""Verify the holdout boundary and frozen threshold provenance in the experiment."""

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from scoring_training import threshold_search as experiment
from scoring_training.train import read_json, write_json


def test_threshold_choices_are_saved_before_any_later_data_is_read(tmp_path, monkeypatch):
    prepared, package, output = [tmp_path / name for name in ("prepared", "package", "output")]
    prepared.mkdir()
    package.mkdir()
    source = {"sourceSha256": "source", "splits": {"calibration": {"years": [2017, 2017]}}, "limitations": []}
    write_json(prepared / "manifest.json", source)
    write_json(package / "manifest.json", {})
    write_json(package / "training.json", {
        "preparedManifestSha256": experiment.sha256_file(prepared / "manifest.json")
    })
    write_json(tmp_path / "lock.json", {"manifestSha256": "pin"})
    reads = []
    frame = pd.DataFrame({
        "LoanStatus": [1, 1, 0, 1, 0], "ApprovalFY": [2017] * 5,
        "BusinessType": ["1"] * 5, "BusinessAge": ["7"] * 5,
    })

    def load_split(_, name):
        reads.append(name)
        if name != "calibration":
            selection = read_json(output / "selection.json")
            assert selection["selectionSplit"] == "calibration"
            assert selection["policies"]["recommended"]["recall"] >= 0.95
            # Deliberately reverse holdout outcomes: the threshold must not adapt.
            return frame.assign(LoanStatus=1 - frame.LoanStatus)
        return frame

    scorer = SimpleNamespace(
        manifest=SimpleNamespace(datasetSha256="source", modelVersion="fixture", naicsMode="full"),
        predict_frame=lambda _: np.array([0.9, 0.7, 0.5, 0.3, 0.1]),
    )
    monkeypatch.setattr(experiment, "ScoringPackage", lambda *_: scorer)
    monkeypatch.setattr(experiment, "load_split", load_split)
    monkeypatch.setattr(experiment, "view", lambda frame, _: frame)
    results = experiment.search(prepared, package, tmp_path / "lock.json", output)
    assert reads == ["calibration", "test", "transfer"]
    frozen = read_json(output / "selection.json")
    assert results["selectionSha256"] == experiment.sha256_file(output / "selection.json")
    for cohort in results["cohorts"].values():
        assert cohort["policies"]["recommended"]["threshold"] == frozen["allThresholds"]["recommended"]
    assert results["cohorts"]["test"]["policies"]["recommended"]["recall"] < 0.95
    with pytest.raises(FileExistsError):
        experiment.search(prepared, package, tmp_path / "lock.json", output)
    write_json(prepared / "manifest.json", {**source, "sourceSha256": "different"})
    with pytest.raises(ValueError, match="provenance"):
        experiment.search(prepared, package, tmp_path / "lock.json", tmp_path / "different")


@pytest.mark.parametrize("floor", [0, -1, 1.01, float("nan")])
def test_invalid_recall_floor_fails_before_reading_files(tmp_path, floor):
    with pytest.raises(ValueError, match="Recall floor"):
        experiment.search(tmp_path, tmp_path, tmp_path, tmp_path, recommended_recall=floor)
