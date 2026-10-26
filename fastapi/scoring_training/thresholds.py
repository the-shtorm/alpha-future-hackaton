"""Exact binary write-off threshold metrics and development-only policy selection."""

import numpy as np


def threshold_table(labels, probability, thresholds=None):
    """Enumerate every attainable decision for p >= threshold, keeping score ties together.

    Explicit 0/1 boundaries include all-positive and (when attainable) all-negative
    decisions. Undefined precision/recall/F-scores use sklearn's zero_division=0.
    Sorting once and cumulative counts avoid rescanning each loan for each cutoff.
    """
    labels, probability = np.asarray(labels), np.asarray(probability, dtype=float)
    if (
        labels.ndim != 1
        or labels.size == 0
        or labels.shape != probability.shape
        or not np.isin(labels, [0, 1]).all()
        or not np.isfinite(probability).all()
        or np.any((probability < 0) | (probability > 1))
    ):
        raise ValueError("Expected nonempty binary labels and finite probabilities in [0, 1]")
    cutoffs = np.asarray(np.r_[0.0, probability, 1.0] if thresholds is None else thresholds, dtype=float)
    if cutoffs.ndim != 1 or not cutoffs.size or not np.isfinite(cutoffs).all() or np.any(
        (cutoffs < 0) | (cutoffs > 1)
    ):
        raise ValueError("Expected finite thresholds in [0, 1]")
    cutoffs = np.unique(cutoffs)
    order = np.argsort(probability, kind="stable")
    prefix = np.r_[0, np.cumsum(labels[order], dtype=np.int64)]
    below = np.searchsorted(probability[order], cutoffs, side="left")
    positives, rows = int(labels.sum()), len(labels)
    tp = positives - prefix[below]
    flagged = rows - below
    fp, fn = flagged - tp, positives - tp
    tn = rows - positives - fp

    def ratio(numerator, denominator):
        return np.divide(
            numerator, denominator, out=np.zeros(len(cutoffs), dtype=float), where=denominator != 0
        )

    precision = ratio(tp, flagged)
    recall = ratio(tp, np.full(len(cutoffs), positives))
    f1, f2 = ratio(2 * tp, 2 * tp + fp + fn), ratio(5 * tp, 5 * tp + fp + 4 * fn)
    fpr = ratio(fp, np.full(len(cutoffs), rows - positives))
    return [
        {
            "threshold": float(cutoff),
            "rows": rows,
            "positives": positives,
            "tp": int(tp[i]),
            "fp": int(fp[i]),
            "fn": int(fn[i]),
            "tn": int(tn[i]),
            "precision": float(precision[i]),
            "recall": float(recall[i]),
            "f1": float(f1[i]),
            "f2": float(f2[i]),
            "falsePositiveRate": float(fpr[i]),
            "flaggedCount": int(flagged[i]),
            "flaggedShare": float(flagged[i] / rows),
        }
        for i, cutoff in enumerate(cutoffs)
    ]


def select_threshold(table, *, metric="f1", min_recall=0.0, tolerance=0.0):
    """Maximize a metric under a recall floor; ties prefer recall, then precision.

    With tolerance > 0, prefer the largest recall within that absolute distance
    from the best metric. Selection must receive development data only.
    """
    if metric not in ("f1", "f2") or not 0 <= min_recall <= 1 or not 0 <= tolerance <= 1:
        raise ValueError("Invalid selection objective")
    if not table or table[0]["positives"] in (0, table[0]["rows"]):
        raise ValueError("Threshold selection requires both classes")
    eligible = [row for row in table if row["recall"] >= min_recall]
    if not eligible:
        raise ValueError("Recall floor is unattainable")
    best = max(row[metric] for row in eligible)
    candidates = [row for row in eligible if row[metric] >= best - tolerance]
    return dict(max(candidates, key=lambda row: (row["recall"], row["precision"], row["threshold"])))


def select_policies(table, recommended_recall=0.95):
    """Freeze comparison objectives before later-cohort evaluation."""
    policies = {
        "maximum_f1": select_threshold(table),
        "maximum_f2": select_threshold(table, metric="f2"),
        "recall_within_1pp_of_best_f1": select_threshold(table, tolerance=0.01),
    }
    for floor in sorted({0.90, 0.95, 0.98, recommended_recall}):
        policies[f"maximum_f1_recall_ge_{floor:g}"] = select_threshold(table, min_recall=floor)
    policies["recommended"] = dict(policies[f"maximum_f1_recall_ge_{recommended_recall:g}"])
    return policies
