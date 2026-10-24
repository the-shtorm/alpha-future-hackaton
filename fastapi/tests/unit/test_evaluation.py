import json

from conftest import ROOT

from app.services.ranker import Ranker
from scripts.evaluate import evaluate


def test_evaluation_labels_and_no_relevant_candidates(encoder):
    products = json.loads((ROOT / "examples/demo-products.json").read_text(encoding="utf-8"))["products"]
    scenarios = json.loads((ROOT / "evaluation/scenarios.seed.json").read_text(encoding="utf-8"))["scenarios"]
    report = evaluate(Ranker(encoder), products, scenarios)
    assert report["preliminary"] and report["evaluatedCount"] == 5
    assert report["noRecommendationCount"] == 5
    assert all(r["recommendedProductIds"] == [] and not r["recommendedHit"] for r in report["scenarios"])
    selected = evaluate(Ranker(encoder, max_cosine_distance=2), products, scenarios)
    assert selected["noRecommendationCount"] == 0
    assert all(r["recommendedCount"] == 3 for r in selected["scenarios"])
    scenarios[0]["proposedRelevantProductIds"] = []
    report = evaluate(Ranker(encoder), products, scenarios[:1])
    assert report["hitRateAt3"] is None and report["noRelevantCandidateCount"] == 1
    scenarios[1]["labelStatus"] = "CONFIRMED"
    assert not evaluate(Ranker(encoder), products, scenarios[1:2])["preliminary"]
