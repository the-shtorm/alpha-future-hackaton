"""Recall-first ranking at existing, independently frozen operating points."""

MIN_RECALL = .84
MIN_PRECISION = .53
TARGET_RECALL = .85
TARGET_PRECISION = .55
RANKING = "accept recall >=0.84 AND precision >=0.53; aim85/55; then maximum precision; ties recall then F1"


def passes_recall_floor(point):
    return point["recall"] >= MIN_RECALL


def passes_target(point):
    return passes_recall_floor(point) and point["precision"] >= MIN_PRECISION


def reaches_goal(point):
    return point["recall"] >= TARGET_RECALL and point["precision"] >= TARGET_PRECISION


def recall_rank_values(point):
    return (int(passes_target(point)), int(passes_recall_floor(point)),
            point["precision"], point["recall"], point["f1"])


def recall_rank(row):
    if row.get("status") != "complete":
        return (-1,)
    return recall_rank_values(row["validation"][row["primaryPolicy"]])
