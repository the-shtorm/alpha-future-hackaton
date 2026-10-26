"""Threshold decisions checked against sklearn and exhaustive direct predictions."""

import numpy as np
import pytest
from scoring_training.thresholds import select_policies, select_threshold, threshold_table
from sklearn.metrics import confusion_matrix, f1_score, fbeta_score, precision_score, recall_score


@pytest.mark.parametrize("seed", [0, 42, 108])
def test_every_unique_threshold_matches_independent_sklearn_metrics(seed):
    rng = np.random.default_rng(seed)
    labels = rng.integers(0, 2, 150)
    probability = rng.integers(0, 11, 150) / 10  # Many ties, including 0 and 1.
    table = threshold_table(labels, probability)
    assert [row["threshold"] for row in table] == sorted(set([0, 1, *probability]))
    for row in table:
        predicted = probability >= row["threshold"]
        tn, fp, fn, tp = confusion_matrix(labels, predicted, labels=[0, 1]).ravel()
        assert [row[key] for key in ("tn", "fp", "fn", "tp")] == [tn, fp, fn, tp]
        assert row["precision"] == pytest.approx(precision_score(labels, predicted, zero_division=0))
        assert row["recall"] == pytest.approx(recall_score(labels, predicted, zero_division=0))
        assert row["f1"] == pytest.approx(f1_score(labels, predicted, zero_division=0))
        assert row["f2"] == pytest.approx(fbeta_score(labels, predicted, beta=2, zero_division=0))
    assert all(a["flaggedCount"] >= b["flaggedCount"] for a, b in zip(table, table[1:], strict=False))


def test_recall_constraints_and_f2_capture_more_positives_than_maximum_f1():
    labels = [1, 1, 0, 0, 1, 0]
    table = threshold_table(labels, [0.9, 0.8, 0.7, 0.6, 0.5, 0.1])
    assert select_threshold(table)["threshold"] == 0.8
    assert select_threshold(table, metric="f2")["threshold"] == 0.5
    assert select_threshold(table, min_recall=0.95)["fn"] == 0
    assert select_threshold(table, tolerance=0.084)["threshold"] == 0.5
    policies = select_policies(table)
    assert policies["recommended"] == policies["maximum_f1_recall_ge_0.95"]
    for floor in (0.9, 0.95, 0.98):
        selected = policies[f"maximum_f1_recall_ge_{floor:g}"]
        assert selected["f1"] == max(row["f1"] for row in table if row["recall"] >= floor)


def test_ties_are_indivisible_and_tied_objectives_prefer_recall():
    table = threshold_table([1, 0, 1, 0], [0.8, 0.8, 0.2, 0.2])
    assert {row["flaggedCount"] for row in table} == {0, 2, 4}
    assert select_threshold(table)["flaggedCount"] == 4
    tied = threshold_table([1, 0, 0, 1], [0.9, 0.8, 0.7, 0.6])
    assert select_threshold(tied)["recall"] == 1


def test_all_flagged_and_none_flagged_decisions_have_defined_zero_division_behavior():
    table = threshold_table([0, 1], [0.2, 0.8], [0, 1])
    assert table[0]["recall"] == 1
    assert table[1]["flaggedCount"] == table[1]["f1"] == table[1]["f2"] == 0
    assert threshold_table([0, 0], [0, 0])[0]["recall"] == 0
    assert threshold_table([1, 1], [0, 0])[0]["falsePositiveRate"] == 0


@pytest.mark.parametrize(
    ("labels", "probability"),
    [([], []), ([1], [0.2, 0.3]), ([[1]], [[0.5]]), ([2], [0.1]),
     ([1], [np.nan]), ([1], [np.inf]), ([1], [-0.1]), ([1], [1.1])],
)
def test_invalid_evaluation_arrays_are_rejected(labels, probability):
    with pytest.raises(ValueError):
        threshold_table(labels, probability)


@pytest.mark.parametrize("cutoffs", [[], [[0.1]], [np.nan], [np.inf], [-0.1], [1.1]])
def test_invalid_cutoffs_are_rejected(cutoffs):
    with pytest.raises(ValueError):
        threshold_table([0, 1], [0.1, 0.9], cutoffs)


def test_selection_rejects_undefined_objectives_and_unattainable_recall():
    table = threshold_table([0, 1], [0.1, 0.9], [1])
    for kwargs in ({"min_recall": 0.9}, {"min_recall": 2}, {"metric": "accuracy"}, {"tolerance": -1}):
        with pytest.raises(ValueError):
            select_threshold(table, **kwargs)
    for labels in ([0, 0], [1, 1]):
        with pytest.raises(ValueError, match="both classes"):
            select_threshold(threshold_table(labels, [0.1, 0.9]))
