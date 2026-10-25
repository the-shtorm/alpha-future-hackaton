"""Point-in-time campaign cohorts and train-only research feature transformations."""

import numpy as np
import pandas as pd
from app.scoring.features import CATEGORICAL, FEATURES

from scoring_training.data import sha256_file
from scoring_training.train import load_split, read_json

FOLDS = {
    "A": {"fitThroughFY": 2015, "validationFY": 2021},
    "B": {"fitThroughFY": 2017, "validationFY": 2023},
    "C": {"fitThroughFY": 2018, "validationFY": 2024},
}
BUNDLES = ("original9_diagnostic_term_unconfirmed", "safe8_without_term", "engineered_safe8")


def source_frame(raw, prepared):
    manifest = read_json(prepared / "manifest.json")
    if sha256_file(raw) != manifest["sourceSha256"]:
        raise ValueError("Campaign source checksum mismatch")
    dates = pd.read_csv(raw)
    frames = [load_split(prepared, name) for name in ("train", "validation", "calibration", "test", "transfer")]
    frame = pd.concat(frames).sort_values("sourceRowIndex").reset_index(drop=True)
    if not np.array_equal(frame.sourceRowIndex, np.arange(len(dates))) or not np.array_equal(
        frame.LoanStatus, dates.LoanStatus
    ):
        raise ValueError("Campaign source row alignment mismatch")

    def date(prefix):
        return pd.to_datetime(dates[[prefix + part for part in ("Year", "Month", "Day")]].rename(
            columns={prefix + part: part.lower() for part in ("Year", "Month", "Day")}
        ), errors="coerce")

    frame["approvalDate"] = date("ApprovalDate")
    frame["outcomeDate"] = date("ChargeOffDate").where(frame.LoanStatus.eq(1), date("PaidInFullDate"))
    if frame[["approvalDate", "outcomeDate"]].isna().any().any():
        raise ValueError("Missing campaign temporal metadata")
    return frame.sort_values(["approvalDate", "sourceRowIndex"]).reset_index(drop=True)


def cohort_frames(frame, fold, window=None):
    """All development outcomes must be known BEFORE the validation FY starts.

    Role periods refer to approvals. The simulation fits all components at one
    cutoff, after a two-year maturation gap for the threshold cohort. This still
    evaluates a selected completed-loan population, not the full originated book.
    """
    spec = FOLDS[fold]
    last = spec["fitThroughFY"]
    cutoff = pd.Timestamp(spec["validationFY"] - 1, 10, 1)
    result, audit = {}, {}
    for role, year in (("fit", last), ("early", last + 1), ("calibration", last + 2),
                       ("threshold", last + 3), ("validation", spec["validationFY"])):
        eligible = frame.ApprovalFY.le(year) if role == "fit" else frame.ApprovalFY.eq(year)
        if role == "fit" and window is not None:
            eligible &= frame.ApprovalFY.ge(last - window + 1)
        known = eligible if role == "validation" else eligible & frame.outcomeDate.lt(cutoff)
        selected = frame.loc[known].copy()
        if len(selected) == 0 or selected.LoanStatus.nunique() != 2:
            raise ValueError(f"Insufficient classes in {fold}/{role}")
        result[role] = selected
        audit[role] = {
            "rows": len(selected), "positives": int(selected.LoanStatus.sum()),
            "excludedOutcomeNotKnown": int(eligible.sum() - known.sum()),
            "firstApproval": str(selected.approvalDate.min().date()),
            "lastApproval": str(selected.approvalDate.max().date()),
        }
    audit["simulationCutoff"] = str(cutoff.date())
    return result, audit


def time_weights(frame, cutoff, half_life):
    if half_life is None:
        return np.ones(len(frame))
    if half_life <= 0:
        raise ValueError("Half life must be positive")
    age = (pd.Timestamp(cutoff) - frame.approvalDate).dt.days.to_numpy() / 365.25
    if np.any(age < 0):
        raise ValueError("Future observations in training")
    weights = np.exp2(-age / half_life)
    return weights / weights.mean()


class FeatureBuilder:
    """No outcome, metadata, future data or term-derived field enters safe bundles."""

    def __init__(self, bundle):
        if bundle not in BUNDLES:
            raise ValueError("Unknown research feature bundle")
        self.bundle = bundle

    def fit(self, frame):
        self.frequencies = {
            name: frame[name].value_counts(normalize=True).to_dict()
            for name in ("NaicsCode", "BusinessAge", "BusinessType")
        }
        self.naics_counts = frame.NaicsCode.value_counts().to_dict()
        self.medians = frame.groupby(frame.NaicsCode.str[:2])[["GrossApproval", "InitialInterestRate"]].median()
        self.amount_median = float(frame.GrossApproval.median())
        self.rate_median = float(frame.InitialInterestRate.median())
        return self

    def transform(self, frame):
        names = [name for name in FEATURES if name != "TermInMonths" or self.bundle.startswith("original9")]
        values = frame.loc[:, names].copy()
        if self.bundle == "engineered_safe8":
            values["logAmount"] = np.log1p(values.GrossApproval)
            for size in (2, 3, 4):
                values[f"naics{size}"] = values.NaicsCode.str[:size]
            for name, frequencies in self.frequencies.items():
                values[f"frequency_{name}"] = values[name].map(frequencies).fillna(0.0)
            values["rareNaics"] = values.NaicsCode.where(values.NaicsCode.map(self.naics_counts).fillna(0) >= 50,
                                                        "RARE_OR_UNKNOWN")
            for left, right in (("naics2", "BusinessAge"), ("BusinessType", "BusinessAge"),
                                ("CollateralInd", "RevolverStatus"), ("naics2", "BusinessType")):
                values[f"{left}_X_{right}"] = values[left] + "|" + values[right]
            sector = values.NaicsCode.str[:2]
            amount = sector.map(self.medians.GrossApproval).fillna(self.amount_median)
            rate = sector.map(self.medians.InitialInterestRate).fillna(self.rate_median)
            values["relativeAmount"] = values.GrossApproval / amount
            values["relativeRate"] = values.InitialInterestRate - rate
        return values

    def fit_transform(self, frame):
        return self.fit(frame).transform(frame)


def categorical_columns(values):
    return [name for name in values if name in CATEGORICAL or values[name].dtype == object]
