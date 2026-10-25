"""Recall-first ranking at existing, independently frozen operating points."""

RANKING = "recall >=0.90 filter, then maximum precision; ties prefer recall then F1; frozen thresholds only"


def passes_recall_floor(point):
    return point["recall"] >= .90


def recall_rank_values(point):
    return (int(passes_recall_floor(point)), point["precision"], point["recall"], point["f1"])


def recall_rank(row):
    if row.get("status") != "complete":
        return (-1,)
    return recall_rank_values(row["validation"][row["primaryPolicy"]])
