"""Recall-first ranking at existing, independently frozen operating points."""

MIN_RECALL = .85
MIN_PRECISION = .55
RANKING = "recall >=0.85 AND precision >=0.55; then maximum precision; ties recall then F1; frozen thresholds only"


def passes_recall_floor(point):
    return point["recall"] >= MIN_RECALL


def passes_target(point):
    return passes_recall_floor(point) and point["precision"] >= MIN_PRECISION


def recall_rank_values(point):
    return (int(passes_target(point)), int(passes_recall_floor(point)),
            point["precision"], point["recall"], point["f1"])


def recall_rank(row):
    if row.get("status") != "complete":
        return (-1,)
    return recall_rank_values(row["validation"][row["primaryPolicy"]])
