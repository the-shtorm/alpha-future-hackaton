import logging
from time import perf_counter

import numpy as np

from app.core.errors import ServiceError
from app.schemas.requests import RankRequest
from app.schemas.responses import Metadata, RankedProduct, RankResponse
from app.services.encoder import Encoder, validate_vectors
from app.services.passage_cache import PassageCache
from app.services.text_builder import build_passage, build_query

logger = logging.getLogger("credit_recsys")


class Ranker:
    def __init__(self, encoder: Encoder, capacity=512):
        self.encoder = encoder
        self.cache = PassageCache(capacity)

    def metadata(self):
        return Metadata(modelId=self.encoder.model_id, modelRevision=self.encoder.revision)

    def rank(self, request: RankRequest) -> RankResponse:
        start = perf_counter()
        ids = [c.product.id for c in request.candidates]
        if len(set(ids)) != len(ids):
            raise ServiceError(422, "DUPLICATE_PRODUCT_ID", "Product identifiers must be unique")
        if not ids:
            return RankResponse(requestId=request.requestId, results=[], metadata=self.metadata())
        texts = [build_query(request.profile), *(build_passage(c.product) for c in request.candidates)]
        for index, length in enumerate(self.encoder.token_lengths(texts)):
            if length > 512:
                detail = {"path": "profile" if index == 0 else f"candidates.{index - 1}.product"}
                if index:
                    detail["productId"] = ids[index - 1]
                raise ServiceError(422, "TEXT_TOO_LONG", "Constructed text exceeds 512 tokens", [detail])
        keys = [self.cache.key(t, self.encoder.model_id, self.encoder.revision) for t in texts[1:]]
        hits, misses = self.cache.hits, self.cache.misses
        vectors = [self.cache.get(k) for k in keys]
        missing = dict.fromkeys(k for k, v in zip(keys, vectors, strict=True) if v is None)
        text_by_key = dict(zip(keys, texts[1:], strict=True))
        if missing:
            encoded = validate_vectors(self.encoder.encode([text_by_key[k] for k in missing]), len(missing))
            missing = dict(zip(missing, encoded, strict=True))
            for k, vector in missing.items():
                self.cache.put(k, vector.copy())
        passages = np.stack([v if v is not None else missing[k] for k, v in zip(keys, vectors, strict=True)])
        query = validate_vectors(self.encoder.encode([texts[0]]), 1)[0]
        scores = passages @ query
        order = sorted(range(len(ids)), key=lambda i: (-float(scores[i]), ids[i]))
        results = []
        for rank, index in enumerate(order, 1):
            candidate = request.candidates[index]
            results.append(
                RankedProduct(
                    productId=ids[index],
                    productVersion=candidate.product.version,
                    rank=rank,
                    similarityScore=round(float(np.clip(scores[index], -1, 1)), 6),
                    isRecommended=rank <= request.topK,
                    eligibilityStatus=candidate.eligibilityStatus,
                    pendingConditions=candidate.pendingConditions,
                )
            )
        logger.info(
            "rank requestId=%r count=%d duration_ms=%.2f cache_hits=%d cache_misses=%d revision=%s contract=rank-v2",
            request.requestId,
            len(ids),
            (perf_counter() - start) * 1000,
            self.cache.hits - hits,
            self.cache.misses - misses,
            self.encoder.revision,
        )
        return RankResponse(requestId=request.requestId, results=results, metadata=self.metadata())
