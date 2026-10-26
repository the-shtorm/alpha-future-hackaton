"""Business feasibility and same-operating-point reporting checked against sklearn."""

import numpy as np
import pytest
from scoring_training.business_thresholds import business_operating_points, select_operating_points
from scoring_training.thresholds import threshold_table
from sklearn.metrics import f1_score, precision_score, recall_score


def test_feasible_optimum_reports_all_three_metrics_from_the_same_threshold():
    labels = np.array([1, 1, 0, 1, 0, 0, 0, 0])
    probability = np.array([0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2])
    result = business_operating_points(labels, probability)
    assert result["status"] == "feasible"
    optimal = result["optimal"]
    assert optimal["threshold"] == 0.6
    predicted = probability >= optimal["threshold"]
    assert optimal["precision"] == precision_score(labels, predicted)
    assert optimal["recall"] == recall_score(labels, predicted)
    assert optimal["f1"] == f1_score(labels, predicted)
    assert optimal["precision"] >= 0.6 and optimal["recall"] >= 0.9
    assert optimal["f1"] >= 0.72
    assert result["metricsAreAveraged"] is False


def test_individually_attainable_constraints_are_not_mistaken_for_joint_feasibility():
    result = business_operating_points([1, 0, 0, 1, 0, 0, 1, 0], [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2])
    assert result["status"] == "infeasible"
    assert result["optimal"] is None
    assert result["feasibleCount"] == 0
    high_precision = result["bestRecallAtPrecisionFloor"]
    high_recall = result["bestPrecisionAtRecallFloor"]
    assert high_precision["precision"] >= 0.6 and high_precision["recall"] < 0.9
    assert high_recall["recall"] >= 0.9 and high_recall["precision"] < 0.6
    assert high_precision["threshold"] != high_recall["threshold"]


def test_empty_precision_frontier_is_explicit_and_tied_probabilities_stay_together():
    result = business_operating_points([0, 0, 1], [0.5, 0.5, 0.5])
    assert result["bestRecallAtPrecisionFloor"] is None
    assert result["optimal"] is None
    assert result["bestPrecisionAtRecallFloor"]["flaggedCount"] == 3


@pytest.mark.parametrize("seed", [0, 11, 42])
def test_exact_business_optimum_matches_brute_force_decisions(seed):
    rng = np.random.default_rng(seed)
    labels = rng.integers(0, 2, 120)
    probability = rng.integers(0, 21, 120) / 20
    expected = []
    for threshold in sorted({0, 1, *probability}):
        predicted = probability >= threshold
        precision = precision_score(labels, predicted, zero_division=0)
        recall = recall_score(labels, predicted, zero_division=0)
        if precision >= 0.6 and recall >= 0.9:
            expected.append((f1_score(labels, predicted), recall, precision, threshold))
    result = business_operating_points(labels, probability)
    if expected:
        row = result["optimal"]
        assert tuple(row[key] for key in ("f1", "recall", "precision", "threshold")) == max(expected)
    else:
        assert result["optimal"] is None


@pytest.mark.parametrize("floor", [-1, 0, 1.01, float("nan"), float("inf")])
@pytest.mark.parametrize("key", ["min_precision", "min_recall"])
def test_invalid_constraints_fail_explicitly(floor, key):
    with pytest.raises(ValueError, match="floors"):
        business_operating_points([0, 1], [0.1, 0.9], **{key: floor})


@pytest.mark.parametrize("table", [[], threshold_table([0, 0], [0.1, 0.9]), threshold_table([1, 1], [0.1, 0.9])])
def test_both_classes_are_required_for_business_selection(table):
    with pytest.raises(ValueError, match="both classes"):
        select_operating_points(table)
