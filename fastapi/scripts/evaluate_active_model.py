"""Evaluate the shipped checkpoint with its current policy, without selecting a new threshold."""

import argparse
import json
from pathlib import Path

from app.core.config import ROOT, Settings
from app.services.encoder import SentenceEncoder
from scripts.calibrate import digest, load_data, metrics, score_split
from scripts.finetune_utils import ranking_summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "evaluation/finetune-test.json")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/active-model-evaluation.json")
    args = parser.parse_args()
    data = json.loads(args.dataset.read_text(encoding="utf-8"))
    scenarios = data["scenarios"]
    catalog, _, _ = load_data()
    settings = Settings(model_variant="finetuned", environment="test", ml_internal_api_key="local-evaluation")
    encoder = SentenceEncoder(settings)
    rows = score_split(encoder, catalog, scenarios)
    report = {
        "modelId": encoder.model_id,
        "artifactSha256": encoder.revision,
        "datasetSha256": digest(args.dataset),
        "maxCosineDistance": settings.recommendation_max_cosine_distance,
        "labelStatus": data.get("labelStatus", "SYNTHETIC_PROPOSED"),
        "notice": "Previously inspected synthetic data with a shared product catalog; diagnostic replay, not a new independent final test. No threshold selection or model changes.",
        "selection": metrics(rows, settings.recommendation_max_cosine_distance),
        "ranking": ranking_summary(rows),
        "scores": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "modelId": report["modelId"],
                "maxCosineDistance": report["maxCosineDistance"],
                "selection": {k: v for k, v in report["selection"].items() if k != "cases"},
                "ranking": report["ranking"],
            }
        )
    )


if __name__ == "__main__":
    main()
