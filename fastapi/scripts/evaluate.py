import argparse
import json
from pathlib import Path

from app.core.config import Settings
from app.schemas.requests import RankRequest
from app.services.encoder import SentenceEncoder
from app.services.ranker import Ranker


def evaluate(ranker, products, scenarios):
    catalog = {p["id"]: p for p in products}
    rows = []
    for scenario in scenarios:
        ids = scenario["candidateProductIds"]
        request = RankRequest.model_validate(
            {
                "requestId": scenario["id"],
                "profile": scenario["profile"],
                "candidates": [
                    {"product": catalog[pid], "eligibilityStatus": "ELIGIBLE", "pendingConditions": []}
                    for pid in ids
                ],
                "topK": 3,
            }
        )
        result = ranker.rank(request)
        relevant = set(scenario["proposedRelevantProductIds"]) & set(ids)
        top = [p.productId for p in result.results[:3]]
        rows.append(
            {
                "id": scenario["id"],
                "labelStatus": scenario["labelStatus"],
                "top3": top,
                "scores": [p.similarityScore for p in result.results[:3]],
                "hitAt3": bool(relevant & set(top)) if relevant else None,
            }
        )
    eligible = [r for r in rows if r["hitAt3"] is not None]
    return {
        "preliminary": any(r["labelStatus"] != "CONFIRMED" for r in rows),
        "hitRateAt3": sum(r["hitAt3"] for r in eligible) / len(eligible) if eligible else None,
        "evaluatedCount": len(eligible),
        "noRelevantCandidateCount": len(rows) - len(eligible),
        "metadata": ranker.metadata().model_dump(),
        "scenarios": rows,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", type=Path, default=Path("evaluation/scenarios.json"))
    parser.add_argument("--products", type=Path, default=Path("examples/demo-products.json"))
    parser.add_argument("--output", type=Path, default=Path("reports/evaluation.json"))
    args = parser.parse_args()
    products = json.loads(args.products.read_text(encoding="utf-8"))
    if isinstance(products, dict):
        products = products["products"]
    scenarios = json.loads(args.scenarios.read_text(encoding="utf-8"))["scenarios"]
    settings = Settings()
    report = evaluate(Ranker(SentenceEncoder(settings)), products, scenarios)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("scenarios", "metadata")}))


if __name__ == "__main__":
    main()
