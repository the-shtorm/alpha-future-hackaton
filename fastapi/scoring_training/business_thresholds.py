"""Development-only operating points under simultaneous precision and recall floors."""

import math

from scoring_training.thresholds import threshold_table


def select_operating_points(table, *, min_precision=0.60, min_recall=0.90):
    """Return complete metric rows at individual thresholds, never metric averages.

    The primary optimum maximizes F1 under BOTH constraints. If none is feasible,
    optimal is None; two explicitly labeled boundary alternatives expose the gap.
    Training, calibration, threshold selection and evaluation must use separate
    chronological cohorts. This function only selects; it does not train models.
    """
    if not all(math.isfinite(value) and 0 < value <= 1 for value in (min_precision, min_recall)):
        raise ValueError("Precision and recall floors must be finite and in (0, 1]")
    if not table or not 0 < table[0]["positives"] < table[0]["rows"]:
        raise ValueError("Threshold selection requires both classes")

    def best(rows, order):
        return dict(max(rows, key=lambda row: tuple(row[key] for key in order))) if rows else None

    precision_eligible = [row for row in table if row["precision"] >= min_precision]
    recall_eligible = [row for row in table if row["recall"] >= min_recall]
    feasible = [row for row in precision_eligible if row["recall"] >= min_recall]
    f1_order = ("f1", "recall", "precision", "threshold")
    return {
        "status": "feasible" if feasible else "infeasible",
        "constraints": {"minPrecision": min_precision, "minRecall": min_recall},
        "candidateCount": len(table),
        "feasibleCount": len(feasible),
        "objective": "maximum F1 under both floors; ties prefer recall, then precision, then threshold",
        "optimal": best(feasible, f1_order),
        "bestRecallAtPrecisionFloor": best(precision_eligible, ("recall", "f1", "precision", "threshold")),
        "bestPrecisionAtRecallFloor": best(recall_eligible, ("precision", "recall", "f1", "threshold")),
        "unconstrainedMaximumF1": best(table, f1_order),
        "metricsAreAveraged": False,
    }


def business_operating_points(labels, probability, *, min_precision=0.60, min_recall=0.90):
    """Enumerate all unique score boundaries for one fitted candidate, then select."""
    return select_operating_points(
        threshold_table(labels, probability), min_precision=min_precision, min_recall=min_recall
    )
