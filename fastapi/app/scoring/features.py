"""One feature implementation shared by CSV ingestion and HTTP inference."""

import math
import re
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Literal

from app.scoring.contracts import BusinessAge, BusinessType, ScoringRequest

FEATURES = (
    "GrossApproval",
    "InitialInterestRate",
    "FixedorVariableInterestInd",
    "TermInMonths",
    "NaicsCode",
    "BusinessType",
    "BusinessAge",
    "RevolverStatus",
    "CollateralInd",
)
NUMERIC = ("GrossApproval", "InitialInterestRate", "TermInMonths")
CATEGORICAL = tuple(name for name in FEATURES if name not in NUMERIC)
BUSINESS_TYPES = {kind: str(index) for index, kind in enumerate(BusinessType, 1)}
BUSINESS_AGES = {age: str(index) for index, age in enumerate(BusinessAge, 1)}
NaicsMode = Literal["full", "prefix2"]


def _number(value: object, field: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"Invalid numeric value: {field}")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"Invalid numeric value: {field}") from None
    if not number.is_finite() or not math.isfinite(float(number)):
        raise ValueError(f"Non-finite numeric value: {field}")
    return number


def _code(value: object, allowed: set[str], field: str) -> str:
    number = _number(value, field)
    if number != number.to_integral_value() or str(int(number)) not in allowed:
        raise ValueError(f"Unknown category: {field}")
    return str(int(number))


def canonical_features(row: Mapping[str, object], naics_mode: NaicsMode = "full") -> dict:
    """Select nine named inputs only; metadata and outcome dates never enter X.

    CSV numeric codes such as '1.0' are accepted only when exactly integral.
    Offline term is not capped to 360: the HTTP contract has its own limit and
    the agreed training population is preserved without silently dropping rows.
    """
    if naics_mode not in ("full", "prefix2"):
        raise ValueError("Unsupported NAICS representation")
    if any(field not in row for field in FEATURES):
        raise ValueError("Missing scoring features")
    amount = _number(row["GrossApproval"], "GrossApproval")
    rate = _number(row["InitialInterestRate"], "InitialInterestRate")
    term = _number(row["TermInMonths"], "TermInMonths")
    if amount <= 0 or rate < 0 or term < 1 or term != term.to_integral_value():
        raise ValueError("Invalid amount, interest rate or term")
    naics = row["NaicsCode"]
    if not isinstance(naics, str) or re.fullmatch(r"[0-9]{6}", naics) is None:
        raise ValueError("NAICS must be a six-digit string")
    result = {
        "GrossApproval": float(amount),
        "InitialInterestRate": float(rate),
        "FixedorVariableInterestInd": row["FixedorVariableInterestInd"],
        "TermInMonths": int(term),
        "NaicsCode": naics if naics_mode == "full" else naics[:2],
        "BusinessType": _code(row["BusinessType"], {"1", "2", "3"}, "BusinessType"),
        "BusinessAge": _code(row["BusinessAge"], {str(i) for i in range(1, 10)}, "BusinessAge"),
        "RevolverStatus": row["RevolverStatus"],
        "CollateralInd": row["CollateralInd"],
    }
    for field, allowed in (
        ("FixedorVariableInterestInd", ("F", "V")),
        ("RevolverStatus", ("Y", "N")),
        ("CollateralInd", ("Y", "N")),
    ):
        if result[field] not in allowed:
            raise ValueError(f"Unknown category: {field}")
    return result


def request_features(request: ScoringRequest, naics_mode: NaicsMode = "full") -> dict:
    return canonical_features(
        {
            "GrossApproval": request.loanAmountUsd,
            "InitialInterestRate": request.initialInterestRatePct,
            "FixedorVariableInterestInd": {"FIXED": "F", "VARIABLE": "V"}[request.interestRateType],
            "TermInMonths": request.termMonths,
            "NaicsCode": request.naicsCode,
            "BusinessType": BUSINESS_TYPES[request.businessType],
            "BusinessAge": BUSINESS_AGES[request.businessAgeCategory],
            "RevolverStatus": "Y" if request.isRevolving else "N",
            "CollateralInd": "Y" if request.hasCollateral else "N",
        },
        naics_mode,
    )


def age_category(full_months: int) -> BusinessAge:
    """Backend-reachable categories; broad historical categories stay distinct."""
    if type(full_months) is not int or full_months < 0:
        raise ValueError("Business age must be non-negative full months")
    for upper, category in (
        (12, BusinessAge.UNDER_ONE),
        (24, BusinessAge.NEW_BROAD),
        (36, BusinessAge.TWO_TO_THREE),
        (48, BusinessAge.THREE_TO_FOUR),
        (60, BusinessAge.FOUR_TO_FIVE),
    ):
        if full_months < upper:
            return category
    return BusinessAge.FIVE_PLUS
