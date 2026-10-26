"""Candidate counts, parameter compatibility and constrained model ranking."""

import concurrent.futures
from pathlib import Path

from scoring_training import campaign
from scoring_training.campaign import refinement, screening, unique_successes
from scoring_training.campaign_fit import result_rank, signature
from scoring_training.data import sha256_file
from scoring_training.train import write_json


def test_exhaustive_screening_is_480_records_with_384_distinct_training_inputs():
    configs = screening()
    assert len(configs) == 480
    assert len({signature(config) for config in configs}) == 384
    assert len({config["id"] for config in configs}) == 480


def test_refinement_samples_360_compatible_configs_for_twelve_parents():
    parents = [{"id": config["id"], "config": config} for config in screening()[:12]]
    configs = refinement(parents)
    assert len(configs) == 360
    for config in configs:
        values = config["parameters"]
        if values["grow_policy"] == "SymmetricTree":
            assert "min_data_in_leaf" not in values
        else:
            assert values["boosting_type"] == "Plain"
        assert ("max_leaves" in values) == (values["grow_policy"] == "Lossguide")
        assert ("bagging_temperature" in values) == (values["bootstrap_type"] == "Bayesian")


def test_feasible_models_are_ranked_by_f1_rather_than_constraint_margin():
    def row(precision, recall):
        return {"status": "complete", "primaryPolicy": "optimal", "validation": {
            "optimal": {"precision": precision, "recall": recall,
                        "f1": 2 * precision * recall / (precision + recall)}
        }}

    assert result_rank(row(0.8, 0.9)) > result_rank(row(0.67, 1))
    assert result_rank(row(0.6, 0.9)) > result_rank(row(0.99, 0.89))


def test_live_limit_bounds_submissions_and_can_be_lowered_without_losing_trials(tmp_path, monkeypatch):
    control = tmp_path / "concurrency.json"
    write_json(control, {"maxActiveFits": 2})
    active, peaks = set(), []
    submitted = []

    class Pool:
        def __init__(self, **kwargs):
            assert kwargs["max_workers"] == 3

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def submit(self, _, config):
            future = concurrent.futures.Future()
            future.config = config
            active.add(future)
            submitted.append(config["id"])
            peaks.append(len(active))
            return future

    def wait(futures, **kwargs):
        future = next(iter(futures))
        config = future.config
        point = {"precision": 0.6, "f1": 0.72, "recall": 0.9, "threshold": 0.2}
        future.set_result({"id": config["id"], "config": config, "status": "complete",
                           "signature": signature(config), "primaryPolicy": "optimal",
                           "validation": {"optimal": point}, "validationTargetPassed": True,
                           "artifact": f"trials/{config['id']}/model.joblib"})
        active.remove(future)
        if len(submitted) == 2:
            write_json(control, {"maxActiveFits": 1})
        return {future}, set(futures) - {future}

    monkeypatch.setattr(campaign.concurrent.futures, "ProcessPoolExecutor", Pool)
    monkeypatch.setattr(campaign.concurrent.futures, "wait", wait)
    results = campaign.execute_batch(screening()[:5], "screening", tmp_path, 3)
    assert len(results) == len(set(submitted)) == 5
    assert max(peaks) == 2
    assert peaks[2:] == [1, 1, 1]


def test_resume_aliases_never_hide_the_actual_fitted_candidate(tmp_path):
    original, alias = screening()[0], screening()[96]
    assert signature(original) == signature(alias)
    source_hashes = {name: sha256_file(Path(campaign.__file__).with_name(name))
                     for name in ("campaign_fit.py", "campaign_data.py", "business_thresholds.py", "thresholds.py")}
    point = {"precision": 0.6, "f1": 0.72, "recall": 0.9, "threshold": 0.2}
    base = {"status": "complete", "signature": signature(original), "primaryPolicy": "optimal",
            "validation": {"optimal": point}, "validationTargetPassed": True,
            "artifact": f"trials/{original['id']}/model.joblib", "implementationSha256": source_hashes}
    for config, link in ((original, alias["id"]), (alias, original["id"])):
        path = tmp_path / "trials" / config["id"]
        path.mkdir(parents=True)
        write_json(path / "result.json", {**base, "id": config["id"], "config": config, "reusedFrom": link})
    results = campaign.execute_batch([original, alias], "screening", tmp_path, 3)
    owners = unique_successes(results)
    assert len(owners) == 1 and owners[0]["id"] == original["id"]
    assert "reusedFrom" not in owners[0]
    assert next(r for r in results if r["id"] == alias["id"])["reusedFrom"] == original["id"]
