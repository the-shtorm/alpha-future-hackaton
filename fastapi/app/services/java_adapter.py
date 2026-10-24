from app.core.errors import ServiceError
from app.schemas.java_exchange import JavaMetadata, JavaRankedProduct, JavaRankRequest, JavaRankResponse
from app.schemas.requests import RankRequest
from app.schemas.responses import RankResponse


def to_internal(body: JavaRankRequest) -> RankRequest:
    seen = set()
    candidates = []
    for candidate in body.candidates:
        if (
            candidate.productId != candidate.product.id
            or candidate.productVersion != candidate.product.version
        ):
            raise ServiceError(422, "VALIDATION_ERROR", "Candidate identifiers do not match product snapshot")
        if candidate.productId in seen:
            raise ServiceError(422, "DUPLICATE_PRODUCT_ID", "Product identifiers must be unique")
        seen.add(candidate.productId)
        product = candidate.product.model_dump(mode="json", exclude={"code", "synthetic"})
        product["targetSectors"] = [
            "TRANSPORT" if sector == "LOGISTICS" else sector for sector in product["targetSectors"]
        ]
        # The ranker uses only product semantics. Restore the full original Java conditions at output.
        candidates.append(
            {"product": product, "eligibilityStatus": candidate.eligibilityStatus, "pendingConditions": []}
        )
    query = body.queryFields
    sector = query.business.sector
    profile = {
        "business": {"sector": "TRANSPORT" if sector == "LOGISTICS" else sector},
        "request": query.request.model_dump(),
        "security": {
            "collateralReady": query.security.collateralReady or "UNKNOWN",
            "guarantorReady": query.security.guarantorReady or "UNKNOWN",
        },
    }
    return RankRequest.model_validate(
        {"requestId": str(body.requestId), "profile": profile, "candidates": candidates, "topK": body.topK}
    )


def to_java(body: JavaRankRequest, ranked: RankResponse) -> JavaRankResponse:
    originals = {(str(c.productId), str(c.productVersion)): c for c in body.candidates}
    results = []
    for item in ranked.results:
        original = originals[(item.productId, item.productVersion)]
        results.append(
            JavaRankedProduct(
                productId=original.productId,
                productVersion=original.productVersion,
                rank=item.rank,
                similarityScore=item.similarityScore,
                isRecommended=item.isRecommended,
                eligibilityStatus=original.eligibilityStatus,
                pendingConditions=original.pendingConditions,
            )
        )
    return JavaRankResponse(
        requestId=body.requestId,
        metadata=JavaMetadata(
            model=ranked.metadata.modelId,
            modelVersion=ranked.metadata.modelRevision,
            queryTemplateVersion=ranked.metadata.queryTemplateVersion,
            passageTemplateVersion=ranked.metadata.passageTemplateVersion,
        ),
        results=results,
    )
