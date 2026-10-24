import json

from conftest import ROOT

from app.services.ranker import Ranker
from scripts.evaluate import evaluate


def test_evaluation_labels_and_no_relevant_candidates(encoder):
    products = json.loads((ROOT / "examples/demo-products.json").read_text(encoding="utf-8"))["products"]
    scenarios = json.loads((ROOT / "evaluation/scenarios.seed.json").read_text(encoding="utf-8"))["scenarios"]
    report = evaluate(Ranker(encoder), products, scenarios)
    assert report["preliminary"] and report["evaluatedCount"] == 5
    scenarios[0]["proposedRelevantProductIds"] = []
    report = evaluate(Ranker(encoder), products, scenarios[:1])
    assert report["hitRateAt3"] is None and report["noRelevantCandidateCount"] == 1
    scenarios[1]["labelStatus"] = "CONFIRMED"
    assert not evaluate(Ranker(encoder), products, scenarios[1:2])["preliminary"]
