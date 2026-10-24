"""Java's automatic exchange envelope. Opaque eligibility metadata is never normalized."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool

from app.schemas.requests import FundingRequest, Product, Readiness, Status

JavaSector = Literal[
    "TRADE", "MANUFACTURING", "SERVICES", "IT", "CONSTRUCTION", "AGRICULTURE", "LOGISTICS", "UNKNOWN"
]
JavaTargetSector = Literal[
    "TRADE", "MANUFACTURING", "SERVICES", "IT", "CONSTRUCTION", "AGRICULTURE", "LOGISTICS"
]


class TransportDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class JavaBusiness(TransportDTO):
    sector: JavaSector | None = None


class JavaSecurity(TransportDTO):
    collateralReady: Readiness | None = None
    guarantorReady: Readiness | None = None


class QueryFields(TransportDTO):
    business: JavaBusiness = Field(default_factory=JavaBusiness)
    request: FundingRequest
    security: JavaSecurity = Field(default_factory=JavaSecurity)


class Dictionaries(TransportDTO):
    version: Literal["query-passage-mvp-2"]
    purposes: dict[str, str]
    sectors: dict[str, str]
    usageModes: dict[str, str]
    readiness: dict[str, str]


class JavaProduct(Product):
    id: UUID
    version: UUID
    code: str = Field(min_length=1, max_length=120)
    synthetic: StrictBool
    targetSectors: list[JavaTargetSector] = Field(
        default_factory=list, max_length=7, json_schema_extra={"uniqueItems": True}
    )


class Condition(TransportDTO):
    code: str
    field: str
    result: Literal["UNKNOWN", "REVIEW"]
    message: str
    actual: JsonValue
    expected: JsonValue


class JavaCandidate(TransportDTO):
    productId: UUID
    productVersion: UUID
    product: JavaProduct
    eligibilityStatus: Status
    pendingConditions: list[Condition]


class JavaRankRequest(TransportDTO):
    schemaVersion: Literal["query-passage-mvp-2"]
    requestId: UUID
    topK: Annotated[
        int, Field(strict=True, ge=1, le=3, description="Maximum recommendations, not result count.")
    ]
    semanticsVersion: Literal["synthetic-semantics-1"]
    queryFields: QueryFields
    dictionaries: Dictionaries
    candidates: list[JavaCandidate] = Field(max_length=100)


class JavaMetadata(TransportDTO):
    model: str = Field(min_length=1, max_length=120)
    modelVersion: str = Field(min_length=1, max_length=120)
    queryTemplateVersion: str = Field(min_length=1, max_length=120)
    passageTemplateVersion: str = Field(min_length=1, max_length=120)


class JavaRankedProduct(TransportDTO):
    productId: UUID
    productVersion: UUID
    rank: int = Field(ge=1)
    similarityScore: float = Field(ge=-1, le=1, allow_inf_nan=False)
    isRecommended: StrictBool
    eligibilityStatus: Status
    pendingConditions: list[Condition]


class JavaRankResponse(TransportDTO):
    requestId: UUID
    metadata: JavaMetadata
    results: list[JavaRankedProduct] = Field(max_length=1000)
