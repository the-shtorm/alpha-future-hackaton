import copy

import numpy as np
import pytest

from app.core.errors import ServiceError
from app.schemas.requests import RankRequest
from app.services.encoder import validate_vectors
from app.services.passage_cache import PassageCache
from app.services.ranker import Ranker


def test_tie_topk_current_metadata_and_cache(payload, encoder):
    ranker = Ranker(encoder, max_cosine_distance=0)
    request = RankRequest.model_validate(payload)
    request.topK = 1
    response = ranker.rank(request)
    assert [p.productId for p in response.results] == sorted(p.product.id for p in request.candidates)
    assert [p.rank for p in response.results] == list(range(1, len(request.candidates) + 1))
    assert sum(p.isRecommended for p in response.results) == 1
    assert all(p.similarityScore == 1 for p in response.results)
    calls = len(encoder.calls)
    request.candidates[0].product.version = "new"
    request.candidates[0].product.name = "Changed name"
    request.candidates[0].eligibilityStatus = "CONDITIONAL"
    response = ranker.rank(request)
    assert len(encoder.calls) == calls + 1  # Query always recomputed, passages reused.
    result = next(p for p in response.results if p.productId == request.candidates[0].product.id)
    assert result.productVersion == "new" and result.eligibilityStatus == "CONDITIONAL"
    assert result.pendingConditions == request.candidates[0].pendingConditions
    request.candidates[0].product.securityNote = "Уточнение обеспечения"
    ranker.rank(request)
    assert len(encoder.calls) == calls + 3


def test_empty_and_duplicates(payload, encoder):
    ranker = Ranker(encoder)
    payload["candidates"] = []
    assert ranker.rank(RankRequest.model_validate(payload)).results == []
    assert encoder.calls == []
    # A duplicate remains a protocol error even though metadata differs.
    import json

    from conftest import ROOT

    raw = json.loads((ROOT / "examples/rank-request.json").read_text(encoding="utf-8"))
    raw["candidates"].append(copy.deepcopy(raw["candidates"][0]))
    with pytest.raises(ServiceError, match="unique"):
        ranker.rank(RankRequest.model_validate(raw))


@pytest.mark.parametrize("index", [0, 1])
def test_long_text_rejected_before_encode(payload, encoder, index):
    encoder.lengths = [10] * (len(payload["candidates"]) + 1)
    encoder.lengths[index] = 513
    with pytest.raises(ServiceError) as error:
        Ranker(encoder).rank(RankRequest.model_validate(payload))
    assert error.value.code == "TEXT_TOO_LONG" and not encoder.calls
    assert bool(error.value.details[0].get("productId")) == bool(index)


def test_real_cosine_sort_before_rounding(payload, encoder):
    def encode(texts):
        values = np.zeros((len(texts), 384), dtype=np.float32)
        for i in range(len(texts)):
            score = 1 if texts[0].startswith("query:") else [-0.4, 0.7, 0.7000001][i % 3]
            values[i, 0] = score
            values[i, 1] = np.sqrt(max(0, 1 - score**2))
        return values

    encoder.encode = encode
    request = RankRequest.model_validate(payload)
    request.candidates = request.candidates[:3]
    result = Ranker(encoder).rank(request)
    assert result.results[-1].similarityScore == -0.4
    if len(result.results) == 3:
        assert result.results[0].productId == request.candidates[2].product.id


def test_lru_and_key_versions():
    cache = PassageCache(1)
    cache.put("a", 1)
    assert cache.get("a") == 1
    cache.put("b", 2)
    assert cache.get("a") is None
    assert cache.get("b") == 2
    base = ("text", "model", "revision", "template", "labels")
    for i in range(5):
        changed = list(base)
        changed[i] += "x"
        assert cache.key(*base) != cache.key(*changed)


@pytest.mark.parametrize("kind", ["shape", "nan", "norm"])
def test_invalid_encoder_vectors(kind):
    vectors = np.zeros((1, 384), dtype=np.float32)
    if kind == "shape":
        vectors = vectors[:, :3]
    elif kind == "nan":
        vectors[0, 0] = np.nan
    with pytest.raises(ValueError, match="invalid"):
        validate_vectors(vectors, 1)


def set_cosines(payload, encoder, scores):
    original = payload["candidates"][0]
    payload["candidates"] = []
    for i in range(len(scores)):
        candidate = copy.deepcopy(original)
        candidate["product"]["id"] = f"controlled-{i}"
        candidate["product"]["targetScenario"] = f"Controlled semantic fixture {i}"
        payload["candidates"].append(candidate)

    def encode(texts):
        values = np.zeros((len(texts), 384), dtype=np.float32)
        for i, text in enumerate(texts):
            score = 1 if text.startswith("query:") else scores[i]
            values[i, 0] = score
            values[i, 1] = np.sqrt(max(0, 1 - score**2))
        return values

    encoder.encode = encode


@pytest.mark.parametrize(
    "distance,count",
    [(None, 0), (0.05, 0), (0.15, 1), (0.25, 2), (0.35, 3), (2, 3)],
)
def test_distance_selects_zero_to_three_but_returns_every_candidate(payload, encoder, distance, count):
    set_cosines(payload, encoder, [0.9, 0.8, 0.7, 0.6])
    response = Ranker(encoder, max_cosine_distance=distance).rank(RankRequest.model_validate(payload))
    assert [p.productId for p in response.results] == [f"controlled-{i}" for i in range(4)]
    assert [p.rank for p in response.results] == [1, 2, 3, 4]
    assert [p.similarityScore for p in response.results] == [0.9, 0.8, 0.7, 0.6]
    assert [p.isRecommended for p in response.results] == [i < count for i in range(4)]
    assert response.metadata.maxCosineDistance == distance
    assert response.metadata.selectionPolicy == "top_k_cosine_distance_v1"
    assert bool(response.metadata.warnings) == (distance is None)


def test_distance_boundary_is_inclusive_and_decided_before_rounding(payload, encoder):
    set_cosines(payload, encoder, [0.4999999, 0.5, 0.5000001])
    response = Ranker(encoder, max_cosine_distance=0.5).rank(RankRequest.model_validate(payload))
    assert [p.productId for p in response.results] == ["controlled-2", "controlled-1", "controlled-0"]
    assert [p.similarityScore for p in response.results] == [0.5, 0.5, 0.5]
    assert [p.isRecommended for p in response.results] == [True, True, False]


def test_topk_is_upper_limit_and_negative_cosine_is_not_automatically_recommended(payload, encoder):
    set_cosines(payload, encoder, [0.9, 0.8, -0.7])
    request = RankRequest.model_validate(payload)
    request.topK = 1
    response = Ranker(encoder, max_cosine_distance=2).rank(request)
    assert len(response.results) == 3 and sum(p.isRecommended for p in response.results) == 1
    response = Ranker(encoder, max_cosine_distance=1).rank(request.model_copy(update={"topK": 3}))
    assert [p.isRecommended for p in response.results] == [True, True, False]


def test_zero_distance_accepts_numerical_drift_above_unit_cosine(payload, encoder):
    set_cosines(payload, encoder, [1.0000001])
    response = Ranker(encoder, max_cosine_distance=0).rank(RankRequest.model_validate(payload))
    assert response.results[0].similarityScore == 1 and response.results[0].isRecommended
