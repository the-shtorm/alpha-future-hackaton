"""Candidate counts, parameter compatibility and constrained model ranking."""

from scoring_training.campaign import refinement, screening
from scoring_training.campaign_fit import result_rank, signature


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
