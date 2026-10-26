"""Chronology and feature leakage checks for actual training campaign inputs."""

import numpy as np
import pandas as pd
import pytest
from scoring_training.campaign_data import BUNDLES, FeatureBuilder, cohort_frames, time_weights


def sample():
    rows = []
    for year in range(2010, 2025):
        for label in (0, 1):
            rows.append({
                "GrossApproval": 10000 + year, "InitialInterestRate": 5.0,
                "FixedorVariableInterestInd": "F", "TermInMonths": 60,
                "NaicsCode": "445110", "BusinessType": "1", "BusinessAge": "7",
                "RevolverStatus": "N", "CollateralInd": "Y", "LoanStatus": label,
                "ApprovalFY": year, "sourceRowIndex": len(rows),
                "approvalDate": pd.Timestamp(year, 1, 1),
                "outcomeDate": pd.Timestamp(year + 1, 1, 1),
            })
    return pd.DataFrame(rows)


def test_development_has_only_known_outcomes_and_disjoint_approval_roles():
    frame = sample()
    frame.loc[len(frame)] = {**frame.iloc[0].to_dict(), "outcomeDate": pd.Timestamp(2025, 1, 1),
                             "ApprovalFY": 2016, "approvalDate": pd.Timestamp(2016, 1, 1),
                             "sourceRowIndex": 999}
    roles, audit = cohort_frames(frame, "B", 3)
    assert roles["fit"].ApprovalFY.min() == 2015
    assert 999 not in set(roles["fit"].sourceRowIndex)
    assert audit["fit"]["excludedOutcomeNotKnown"] == 1
    cutoff = pd.Timestamp(audit["simulationCutoff"])
    for role, values in roles.items():
        if role != "validation":
            assert values.outcomeDate.lt(cutoff).all()
        for other, other_values in roles.items():
            if other != role:
                assert not set(values.sourceRowIndex) & set(other_values.sourceRowIndex)
    assert roles["validation"].ApprovalFY.eq(2023).all()


@pytest.mark.parametrize("bundle", BUNDLES)
def test_feature_statistics_are_train_only_and_safe_bundles_exclude_term(bundle):
    frame = sample()
    builder = FeatureBuilder(bundle).fit(frame)
    changed = frame.iloc[:1].copy()
    changed["NaicsCode"] = "999999"
    values = builder.transform(changed)
    assert not set(values) & {"LoanStatus", "ApprovalFY", "sourceRowIndex", "approvalDate", "outcomeDate"}
    assert ("TermInMonths" in values) == bundle.startswith("original9")
    if bundle == "engineered_safe8":
        assert values.frequency_NaicsCode.iloc[0] == 0
        assert values.rareNaics.iloc[0] == "RARE_OR_UNKNOWN"
    mutated = changed.assign(LoanStatus=1 - changed.LoanStatus, TermInMonths=9999)
    if not bundle.startswith("original9"):
        pd.testing.assert_frame_equal(values, builder.transform(mutated))


def test_time_weight_decay_is_based_on_simulated_training_cutoff():
    frame = sample().iloc[:4]
    weights = time_weights(frame, "2022-10-01", 3)
    assert weights.mean() == pytest.approx(1)
    assert weights[0] < weights[-1]
    np.testing.assert_array_equal(time_weights(frame, "2022-10-01", None), np.ones(4))
    with pytest.raises(ValueError):
        time_weights(frame, "2000-01-01", 3)
