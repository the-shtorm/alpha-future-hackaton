"""Versioned scoring transport; financial decisions remain in Spring Boot."""

from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator, model_validator

SCHEMA_VERSION = "sba-scoring-1"
FEATURE_VERSION = "sba-features-1"


class BusinessType(StrEnum):
    CORPORATION = "CORPORATION"
    INDIVIDUAL = "INDIVIDUAL"
    PARTNERSHIP = "PARTNERSHIP"


class BusinessAge(StrEnum):
    STARTUP = "Startup, Loan Funds will Open Business"
    UNDER_ONE = "New, Less than 1 Year old"
    NEW_BROAD = "New Business or 2 years or less"
    TWO_TO_THREE = "Less than 3 years old but at least 2"
    THREE_TO_FOUR = "Less than 4 years old but at least 3"
    FOUR_TO_FIVE = "Less than 5 years old but at least 4"
    FIVE_PLUS = "Existing, 5 or more years"
    EXISTING_BROAD = "Existing or more than 2 years old"
    OWNERSHIP_CHANGE = "Change of Ownership"


class ScoringDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True)


class ScoringRequest(ScoringDTO):
    schemaVersion: Literal["sba-scoring-1"]
    requestId: UUID
    loanAmountUsd: str = Field(pattern=r"^(0|[1-9][0-9]*)\.[0-9]{2}$", max_length=24)
    termMonths: Annotated[StrictInt, Field(ge=1, le=360)]
    initialInterestRatePct: str = Field(pattern=r"^(0|[1-9][0-9]*)(\.[0-9]{1,5})?$", max_length=24)
    interestRateType: Literal["FIXED", "VARIABLE"]
    isRevolving: StrictBool
    hasCollateral: StrictBool
    businessType: BusinessType
    businessAgeCategory: BusinessAge
    naicsCode: str = Field(pattern=r"^[0-9]{6}$")

    @field_validator("loanAmountUsd")
    @classmethod
    def positive_amount(cls, value: str) -> str:
        if Decimal(value) <= 0:
            raise ValueError("Amount must be positive")
        return value


def probability_score(probability: Decimal | float) -> int:
    """Round only the displayed score, preserving the probability used by policy."""
    value = Decimal(str(probability))
    if not value.is_finite() or not 0 <= value <= 1:
        raise ValueError("Probability must be finite and in [0, 1]")
    return int(((Decimal(1) - value) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


class ScoringResponse(ScoringDTO):
    schemaVersion: Literal["sba-scoring-1"]
    requestId: UUID
    sbaDefaultProbability: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False, strict=True)]
    score: Annotated[StrictInt, Field(ge=0, le=100)]
    modelVersion: str = Field(min_length=1, max_length=120)
    featureVersion: Literal["sba-features-1"]
    calibrationVersion: str = Field(min_length=1, max_length=120)
    domainStatus: Literal["IN_RANGE", "EXTRAPOLATION"]
    isDemo: Literal[True]
    warnings: list[Annotated[str, Field(min_length=1, max_length=120)]]

    @model_validator(mode="after")
    def consistent_score(self):
        if self.score != probability_score(self.sbaDefaultProbability):
            raise ValueError("Score must match probability")
        return self
