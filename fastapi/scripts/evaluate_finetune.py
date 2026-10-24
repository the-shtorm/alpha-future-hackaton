"""CPU evaluation; choose calibration thresholds and freeze them before evaluating fresh final data."""

import argparse
import gc
import json
from pathlib import Path

from app.core.config import ROOT, Settings
from app.services.encoder import SentenceEncoder
from scripts.calibrate import digest, load_data, metrics, score_split
from scripts.finetune_utils import (
    choose_f05_distance,
    ranking_summary,
    read_scenarios,
    score_model,
    verify_finetuned_manifest,
)


def load_candidate(directory):
    from sentence_transformers import SentenceTransformer

    manifest = verify_finetuned_manifest(directory)
    model = SentenceTransformer(str(directory), device="cpu", local_files_only=True, trust_remote_code=False)
    model.max_seq_length, model.default_prompt_name = 512, None
    return model, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=ROOT / "models/e5-credit-finetune-v1/final")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/e5-finetune-evaluation.json")
    args = parser.parse_args()
    catalog, calibration, _ = load_data()
    development = read_scenarios("holdout.json") + read_scenarios("reranker-test.json")
    print("CPU baseline: calibration and development", flush=True)
    baseline = SentenceEncoder(Settings(model_variant="base", recommendation_max_cosine_distance=None))
    scores = {
        "baseline": {
            "calibration": score_split(baseline, catalog, calibration["scenarios"]),
            "development": score_split(baseline, catalog, development),
        }
    }
    del baseline
    gc.collect()
    print("CPU fine-tuned model: calibration and development", flush=True)
    model, manifest = load_candidate(args.model)
    scores["fineTuned"] = {
        "calibration": score_model(model, catalog, calibration["scenarios"]),
        "development": score_model(model, catalog, development),
    }
    thresholds = {name: choose_f05_distance(value["calibration"]) for name, value in scores.items()}
    policy = {
        "objective": "Maximum calibration micro F0.5; ties higher precision then smaller distance",
        "thresholds": thresholds,
        "fineTunedArtifactSha256": manifest["artifactSha256"],
        "inputSha256": {
            name: digest(ROOT / "evaluation" / name)
            for name in (
                "finetune-train.json",
                "calibration.json",
                "holdout.json",
                "reranker-test.json",
                "finetune-test.json",
            )
        },
        "labelStatus": "SYNTHETIC_PROPOSED",
        "notice": "Independent per-model thresholds; final data do not select weights or thresholds. Full ranked candidate lists preserved.",
    }
    frozen = args.output.with_name("e5-finetune-frozen-policies.json")
    frozen.parent.mkdir(parents=True, exist_ok=True)
    frozen.write_text(json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    frozen_sha = digest(frozen)
    print(json.dumps({"frozenMaxCosineDistances": thresholds}), flush=True)
    final = read_scenarios("finetune-test.json")
    scores["fineTuned"]["finalTest"] = score_model(model, catalog, final)
    del model
    gc.collect()
    baseline = SentenceEncoder(Settings(model_variant="base", recommendation_max_cosine_distance=None))
    scores["baseline"]["finalTest"] = score_split(baseline, catalog, final)
    assert digest(frozen) == frozen_sha
    report = {
        "policy": policy,
        "frozenPolicySha256": frozen_sha,
        "metrics": {
            name: {
                split: {"selection": metrics(rows, thresholds[name]), "ranking": ranking_summary(rows)}
                for split, rows in value.items()
            }
            for name, value in scores.items()
        },
        "scores": scores,
        "trainingSummary": json.loads(
            (args.model.parent / "training-summary.json").read_text(encoding="utf-8")
        ),
        "notice": "Local fine-tuning experiment. Production weights/threshold unchanged; synthetic labels require human review.",
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                name: {
                    "selection": {k: v for k, v in parts["finalTest"]["selection"].items() if k != "cases"},
                    "ranking": parts["finalTest"]["ranking"],
                }
                for name, parts in report["metrics"].items()
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
