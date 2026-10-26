"""Apply the current development target in new fits, before later-year scoring."""

from contextlib import contextmanager

from scoring_training.business_thresholds import business_operating_points
from scoring_training.campaign_priority import TARGET_PRECISION, TARGET_RECALL


def select_thresholds(labels, probability):
    return business_operating_points(labels, probability, min_precision=TARGET_PRECISION, min_recall=TARGET_RECALL)


def choose_operating_point(selection):
    for policy in ("bestPrecisionAtRecallFloor", "bestRecallAtPrecisionFloor", "unconstrainedMaximumF1"):
        if selection.get(policy) is not None:
            return policy, selection[policy]
    raise ValueError("No development operating point")


@contextmanager
def new_fit_target():
    from scoring_training import campaign_fit

    old_selection, old_primary = campaign_fit.business_operating_points, campaign_fit.primary_point
    campaign_fit.business_operating_points, campaign_fit.primary_point = select_thresholds, choose_operating_point
    try:
        yield
    finally:
        campaign_fit.business_operating_points, campaign_fit.primary_point = old_selection, old_primary
