"""Resolve/verify the configured scoring model without loading E5 or training anything."""

import argparse
import json

from app.api.routes.scoring import load_scoring
from app.core.config import ROOT, Settings
from app.scoring.contracts import ScoringRequest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", help="Override SCORING_MODEL_PATH: local directory or HF address")
    parser.add_argument("--cache-dir")
    parser.add_argument("--local-files-only", action="store_true", default=None)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    options = {"environment": "test", "ml_internal_api_key": "scoring-package-verification"}
    for name, value in vars(args).items():
        if value is not None and name != "smoke":
            options[
                {
                    "model_path": "scoring_model_path",
                    "cache_dir": "hf_cache_dir",
                    "local_files_only": "hf_local_files_only",
                }[name]
            ] = value
    try:
        scorer = load_scoring(Settings(**options))
        result = {
            "verified": True,
            "modelVersion": scorer.manifest.modelVersion,
            "calibrationVersion": scorer.manifest.calibrationVersion,
            "operatingThreshold": scorer.manifest.operatingThreshold,
        }
        if args.smoke:
            request = ScoringRequest.model_validate_json(
                (ROOT / "examples/scoring-request.json").read_bytes()
            )
            result["smoke"] = scorer.evaluate(request).model_dump(mode="json")
    except Exception:
        parser.exit(
            1, "Scoring verification failed; check source, access, manifest and dependency versions.\n"
        )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
