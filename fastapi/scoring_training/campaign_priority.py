"""Recall-first ranking at existing, independently frozen operating points."""

RANKING = "precision >=0.60 first; then recall, F1, precision; frozen thresholds only"


def recall_rank_values(point):
    return (int(point["precision"] >= .60), point["recall"], point["f1"], point["precision"])


def recall_rank(row):
    if row.get("status") != "complete":
        return (-1,)
    return recall_rank_values(row["validation"][row["primaryPolicy"]])
