from typing import Annotated, Literal

from pydantic import Field

from app.core.config import VERSIONS
from app.schemas.requests import DTO, PendingCondition, Status


class Metadata(DTO):
    modelId: str = Field(min_length=1, max_length=120)
    modelRevision: str = Field(min_length=1, max_length=120)
    queryTemplateVersion: Literal["query-v2"] = VERSIONS["queryTemplateVersion"]
    passageTemplateVersion: Literal["passage-v2"] = VERSIONS["passageTemplateVersion"]
    labelsVersion: Literal["ru-v2"] = VERSIONS["labelsVersion"]
    contractVersion: Literal["rank-v2"] = VERSIONS["contractVersion"]
    rankingMode: Literal["semantic_only"] = "semantic_only"
    scoreType: Literal["cosine_similarity"] = "cosine_similarity"
    selectionPolicy: Literal["top_k_cosine_distance_v1"] = "top_k_cosine_distance_v1"
    maxCosineDistance: float | None = Field(default=None, ge=0, le=2, allow_inf_nan=False)
    warnings: list[Annotated[str, Field(min_length=1, max_length=300)]] = Field(default_factory=list)


class RankedProduct(DTO):
    productId: str = Field(min_length=1, max_length=120)
    productVersion: str = Field(min_length=1, max_length=80)
    rank: int = Field(ge=1)
    similarityScore: float = Field(ge=-1, le=1)
    isRecommended: bool
    eligibilityStatus: Status
    pendingConditions: list[PendingCondition] = Field(max_length=20, json_schema_extra={"uniqueItems": True})


class RankResponse(DTO):
    requestId: str = Field(min_length=1, max_length=120)
    results: list[RankedProduct] = Field(max_length=100)
    metadata: Metadata


class ErrorBody(DTO):
    code: str
    message: str
    details: list[dict]


class ErrorResponse(DTO):
    error: ErrorBody
    requestId: str | None


ERROR_RESPONSES = {status: {"model": ErrorResponse} for status in (401, 413, 422, 503, 500)}


class ModelInfo(DTO):
    modelId: str
    modelRevision: str
    dimension: Literal[384]
    maxSeqLength: Literal[512]
    device: Literal["cpu"]
    queryTemplateVersion: Literal["query-v2"]
    passageTemplateVersion: Literal["passage-v2"]
    labelsVersion: Literal["ru-v2"]
    contractVersion: Literal["rank-v2"]
    selectionPolicy: Literal["top_k_cosine_distance_v1"] = "top_k_cosine_distance_v1"
    maxCosineDistance: float | None = Field(default=None, ge=0, le=2, allow_inf_nan=False)
