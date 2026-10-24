import json
import unicodedata
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from app.core.config import ROOT

PRODUCT_RULES = json.loads((ROOT / "contracts/rank-request.schema.json").read_text(encoding="utf-8"))[
    "properties"
]["candidates"]["items"]["properties"]["product"]["allOf"]

Sector = Literal[
    "TRADE",
    "MANUFACTURING",
    "SERVICES",
    "AGRICULTURE",
    "CONSTRUCTION",
    "TRANSPORT",
    "IT",
    "HOSPITALITY",
    "OTHER",
    "UNKNOWN",
]
TargetSector = Literal[
    "TRADE", "MANUFACTURING", "SERVICES", "AGRICULTURE", "CONSTRUCTION", "TRANSPORT", "IT", "HOSPITALITY"
]
Purpose = Literal[
    "WORKING_CAPITAL",
    "CASH_GAP",
    "EQUIPMENT",
    "TRANSPORT",
    "COMMERCIAL_PROPERTY",
    "CONTRACT_EXECUTION",
    "REFINANCING",
    "DEVELOPMENT",
]
Usage = Literal["ONE_TIME", "IN_PARTS", "ACCOUNT_RESERVE"]
Readiness = Literal["YES", "NO", "DISCUSS", "UNKNOWN"]
Requirement = Literal["NONE", "REQUIRED", "CONDITIONAL"]
Status = Literal["ELIGIBLE", "CONDITIONAL"]


def clean_text(value: str) -> str:
    text = unicodedata.normalize("NFC", value)
    text = "".join(" " if unicodedata.category(c).startswith("C") else c for c in text)
    return " ".join(text.split())


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def normalize(cls, value):
        return clean_text(value) if isinstance(value, str) else value


class Business(DTO):
    sector: Sector | None


class FundingRequest(DTO):
    purpose: Purpose
    usageMode: Literal["ONE_TIME", "IN_PARTS", "ACCOUNT_RESERVE", "UNKNOWN"]
    description: Annotated[str, Field(max_length=500)] | None = None

    @field_validator("description")
    @classmethod
    def empty_as_none(cls, value):
        return value or None


class Security(DTO):
    collateralReady: Readiness
    guarantorReady: Readiness


class Profile(DTO):
    business: Business
    request: FundingRequest
    security: Security


class Product(DTO):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"allOf": PRODUCT_RULES})
    id: str = Field(min_length=1, max_length=120)
    version: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    type: Literal["TERM_LOAN", "REVOLVING_CREDIT_LINE", "NON_REVOLVING_CREDIT_LINE", "OVERDRAFT"]
    purposes: list[Purpose] = Field(min_length=1, max_length=8, json_schema_extra={"uniqueItems": True})
    usageModes: list[Usage] = Field(min_length=1, max_length=3, json_schema_extra={"uniqueItems": True})
    targetScenario: str = Field(min_length=1, max_length=500)
    targetSectors: list[TargetSector] = Field(
        default_factory=list, max_length=8, json_schema_extra={"uniqueItems": True}
    )
    specialization: Annotated[str, Field(max_length=200)] | None = None
    collateralRequirement: Requirement
    guarantorRequirement: Requirement
    securityNote: Annotated[str, Field(max_length=200)] | None = None

    @field_validator("purposes", "usageModes", "targetSectors")
    @classmethod
    def unique_sorted(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Array items must be unique")
        return sorted(value)

    @field_validator("specialization", "securityNote")
    @classmethod
    def empty_as_none(cls, value):
        return value or None

    @model_validator(mode="after")
    def conditional_note(self):
        if "CONDITIONAL" in (self.collateralRequirement, self.guarantorRequirement) and not self.securityNote:
            raise ValueError("Conditional security requires securityNote")
        return self


class PendingCondition(DTO):
    code: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=300)


class Candidate(DTO):
    product: Product
    eligibilityStatus: Status
    pendingConditions: list[PendingCondition] = Field(max_length=20, json_schema_extra={"uniqueItems": True})

    @field_validator("pendingConditions")
    @classmethod
    def unique_conditions(cls, value):
        if len({(c.code, c.message) for c in value}) != len(value):
            raise ValueError("Conditions must be unique")
        return value


class RankRequest(DTO):
    requestId: str = Field(min_length=1, max_length=120)
    profile: Profile
    candidates: list[Candidate] = Field(max_length=100)
    topK: Annotated[
        StrictInt, Field(ge=1, le=3, description="Maximum recommendations; all candidates are ranked.")
    ] = 3
