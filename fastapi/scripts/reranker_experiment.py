"""Offline model/threshold comparison; freezes the primary policy before opening the new final test."""

import argparse
import hashlib
import json
import os
import platform
import threading
import time
from pathlib import Path

import numpy as np
import psutil

from app.core.config import ROOT, Settings
from app.schemas.requests import Profile, RankRequest
from app.services.encoder import SentenceEncoder
from app.services.ranker import Ranker
from app.services.text_builder import build_passage, build_query
from scripts.calibrate import digest, load_data, metrics, score_split

CRITERIA = ("f1", "f0.5", "precision_at_recall_50", "recall_at_precision_80")
PROTOCOL = {
    "version": "reranker-comparison-1",
    "calibration": "existing 180 synthetic profiles; threshold selection only",
    "development": "old 90-profile holdout, now explicitly development; primary model/criterion selection",
    "finalTest": "90 fresh sealed profiles; evaluated only after primary policy is saved",
    "primaryRule": "Highest development F0.5 among feasible policies with recall >= 0.30 and coverage >= 0.25; ties by precision then F1 then stable experiment id.",
    "precisionConstraint": "precision >= 0.80, recall > 0, coverage >= 0.25; report infeasible if no threshold qualifies",
    "input": "Same full v2 text fields for both models. Remove only E5 query:/passage: prefixes for CrossEncoder.",
    "labels": "SYNTHETIC_PROPOSED, not expert-confirmed; not financial eligibility or approval",
    "runtime": "CPU float32, batch=4, torch threads=2, interop=1; all candidates reranked, none dropped",
}


class LocalReranker:
    def __init__(self, directory=ROOT / "models/mmarco-minilm-reranker"):
        lock = json.loads((ROOT / "config/reranker-experiment.lock.json").read_text(encoding="utf-8"))
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        if manifest["modelId"] != lock["modelId"] or manifest["revision"] != lock["revision"]:
            raise ValueError("Reranker manifest differs from the pinned experiment")
        for name, expected in manifest["checksums"].items():
            path = (directory / name).resolve()
            if not path.is_relative_to(directory.resolve()) or path.suffix not in (
                ".json",
                ".safetensors",
                ".model",
                ".md",
            ):
                raise ValueError("Unsafe reranker artifact")
            with path.open("rb") as source:
                actual = hashlib.file_digest(source, "sha256").hexdigest()
            if actual != expected:
                raise ValueError("Reranker checksum mismatch")
        os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", TOKENIZERS_PARALLELISM="false")
        import torch
        from sentence_transformers import CrossEncoder

        torch.set_num_threads(2)
        if torch.get_num_interop_threads() != 1:
            torch.set_num_interop_threads(1)
        self.model = CrossEncoder(
            str(directory),
            device="cpu",
            local_files_only=True,
            trust_remote_code=False,
            max_length=512,
            activation_fn=torch.nn.Identity(),
            model_kwargs={"torch_dtype": torch.float32, "use_safetensors": True},
        )
        self.model_id = manifest["modelId"]
        self.revision = manifest["revision"]

    def predict(self, pairs):
        if not pairs:
            return np.empty(0, dtype=np.float32)
        lengths = self.model.tokenizer(
            [p[0] for p in pairs],
            [p[1] for p in pairs],
            add_special_tokens=True,
            truncation=False,
            padding=False,
        )["input_ids"]
        if max(map(len, lengths)) > 512:
            raise ValueError("CrossEncoder pair exceeds 512 tokens")
        values = np.asarray(
            self.model.predict(pairs, batch_size=4, show_progress_bar=False, convert_to_numpy=True)
        ).reshape(-1)
        if values.shape != (len(pairs),) or not np.isfinite(values).all():
            raise ValueError("Invalid CrossEncoder logits")
        return values


def score_reranker(encoder, catalog, scenarios):
    passages = {code: build_passage(p).removeprefix("passage: ") for code, p in catalog.items()}
    pairs, spans = [], []
    for s in scenarios:
        raw = json.loads(json.dumps(s["profile"]))
        if raw["business"]["sector"] == "LOGISTICS":
            raw["business"]["sector"] = "TRANSPORT"
        query = build_query(Profile.model_validate(raw)).removeprefix("query: ")
        start = len(pairs)
        pairs.extend((query, passages[c]) for c in s["candidateProductCodes"])
        spans.append((start, len(pairs)))
    logits = encoder.predict(pairs)
    rows = []
    for s, (start, end) in zip(scenarios, spans, strict=True):
        codes, values = s["candidateProductCodes"], logits[start:end]
        order = sorted(range(len(codes)), key=lambda i: (-float(values[i]), catalog[codes[i]].id))
        rows.append(
            {
                "id": s["id"],
                "familyId": s["familyId"],
                "intent": s["intent"],
                "relevant": s["relevantProductCodes"],
                "ranking": [{"code": codes[i], "score": float(values[i])} for i in order],
            }
        )
    return rows


def selection_metrics(rows, min_score):
    result = metrics(rows, 1 - min_score)
    tp, fp, fn = result["tp"], result["fp"], result["fn"]
    result["f0.5"] = 1.25 * tp / (1.25 * tp + fp + 0.25 * fn) if tp + fp + fn else 0
    result["coverage"] = 1 - result["abstentionCount"] / len(rows) if rows else 0
    result["noRelevantRejectionRate"] = (
        result["noRelevantAbstentionCount"] / result["noRelevantCount"] if result["noRelevantCount"] else None
    )
    return result


def ranking_metrics(rows):
    ndcg, reciprocal = [], []
    for row in rows:
        relevant = set(row["relevant"])
        if not relevant:
            continue
        gains = [int(p["code"] in relevant) for p in row["ranking"]]
        dcg = sum(g / np.log2(i + 2) for i, g in enumerate(gains[:3]))
        ideal = sum(1 / np.log2(i + 2) for i in range(min(3, len(relevant))))
        ndcg.append(dcg / ideal)
        reciprocal.append(next((1 / (i + 1) for i, g in enumerate(gains) if g), 0))
    return {
        "ndcgAt3": float(np.mean(ndcg)) if ndcg else None,
        "mrr": float(np.mean(reciprocal)) if reciprocal else None,
        "rankEvaluatedCount": len(ndcg),
    }


def choose_policies(rows):
    scores = sorted({p["score"] for r in rows for p in r["ranking"][:3]})
    if not scores:
        raise ValueError("No calibration scores")
    candidates = [
        scores[0] - 1,
        *[(a + b) / 2 for a, b in zip(scores, scores[1:], strict=False)],
        scores[-1] + 1,
    ]
    table = [
        {"minScore": t, **{k: v for k, v in selection_metrics(rows, t).items() if k != "cases"}}
        for t in candidates
    ]
    policies = {}
    for criterion in CRITERIA:
        feasible = table
        if criterion == "precision_at_recall_50":
            feasible = [r for r in table if r["recall"] >= 0.50]
            fields = ("precision", "f0.5", "minScore")
        elif criterion == "recall_at_precision_80":
            feasible = [
                r for r in table if r["precision"] >= 0.80 and r["recall"] > 0 and r["coverage"] >= 0.25
            ]
            fields = ("recall", "precision", "minScore")
        else:
            fields = (criterion, "precision", "minScore")
        policies[criterion] = (
            max(feasible, key=lambda r, fields=fields: tuple(r[f] for f in fields)) if feasible else None
        )
    return policies, table


def select_primary(experiments):
    feasible = [
        e for e in experiments if e["development"]["recall"] >= 0.30 and e["development"]["coverage"] >= 0.25
    ]
    if not feasible:
        raise ValueError("No experiment meets the predeclared primary-selection constraints")
    return max(
        feasible,
        key=lambda e: (
            e["development"]["f0.5"],
            e["development"]["precision"],
            e["development"]["f1"],
            e["id"],
        ),
    )["id"]


def benchmark(encoder, reranker, catalog, scenario, iterations=8):
    raw = json.loads(json.dumps(scenario["profile"]))
    if raw["business"]["sector"] == "LOGISTICS":
        raw["business"]["sector"] = "TRANSPORT"
    request = RankRequest.model_validate(
        {
            "requestId": "benchmark-all-15",
            "profile": raw,
            "topK": 3,
            "candidates": [
                {"product": p.model_dump(), "eligibilityStatus": "ELIGIBLE", "pendingConditions": []}
                for p in catalog.values()
            ],
        }
    )
    ranker = Ranker(encoder)
    pairs = [
        (build_query(request.profile).removeprefix("query: "), build_passage(p).removeprefix("passage: "))
        for p in catalog.values()
    ]
    ranker.rank(request)
    reranker.predict(pairs)
    timings = {"e5Warm": [], "crossEncoderOnly": [], "e5PlusCrossEncoder": []}
    for _ in range(iterations):
        start = time.perf_counter()
        ranker.rank(request)
        timings["e5Warm"].append((time.perf_counter() - start) * 1000)
        start = time.perf_counter()
        reranker.predict(pairs)
        timings["crossEncoderOnly"].append((time.perf_counter() - start) * 1000)
        start = time.perf_counter()
        ranker.rank(request)
        reranker.predict(pairs)
        timings["e5PlusCrossEncoder"].append((time.perf_counter() - start) * 1000)
    return {
        "candidateCount": 15,
        "iterations": iterations,
        "transport": "model stages only; excludes HTTP and Java",
        "timings": {
            k: {"p50Ms": float(np.percentile(v, 50)), "p95Ms": float(np.percentile(v, 95))}
            for k, v in timings.items()
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/reranker-experiment.json")
    args = parser.parse_args()
    process = psutil.Process()
    peak = [process.memory_info().rss]
    stop = threading.Event()

    def sample():
        while not stop.wait(0.02):
            peak[0] = max(peak[0], process.memory_info().rss)

    monitor = threading.Thread(target=sample, daemon=True)
    monitor.start()
    try:
        catalog, calibration, development = load_data()
        input_hashes = {
            name: digest(ROOT / "evaluation" / name)
            for name in ("calibration.json", "holdout.json", "reranker-test.json", "backend-products.json")
        }
        protocol_path = args.output.with_name("reranker-protocol.json")
        protocol_path.parent.mkdir(parents=True, exist_ok=True)
        protocol_path.write_text(
            json.dumps({**PROTOCOL, "inputSha256": input_hashes}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print("Scoring E5 calibration/development", flush=True)
        start = time.perf_counter()
        encoder = SentenceEncoder(
            Settings(
                model_path=None,
                model_source="local",
                model_variant="base",
                recommendation_max_cosine_distance=None,
            )
        )
        e5_load = time.perf_counter() - start
        scored = {
            "e5": {
                "calibration": score_split(encoder, catalog, calibration["scenarios"]),
                "development": score_split(encoder, catalog, development["scenarios"]),
            }
        }
        print("Loading pinned offline CrossEncoder; scoring calibration/development", flush=True)
        start = time.perf_counter()
        reranker = LocalReranker()
        ce_load = time.perf_counter() - start
        scored["cross_encoder"] = {
            "calibration": score_reranker(reranker, catalog, calibration["scenarios"]),
            "development": score_reranker(reranker, catalog, development["scenarios"]),
        }
        experiments, searches, infeasible = [], {}, []
        for model, splits in scored.items():
            policies, searches[model] = choose_policies(splits["calibration"])
            for criterion, policy in policies.items():
                if policy is None:
                    infeasible.append(model + "/" + criterion)
                    continue
                threshold = policy["minScore"]
                experiments.append(
                    {
                        "id": model + "/" + criterion,
                        "model": model,
                        "criterion": criterion,
                        "scoreType": "cosine_similarity" if model == "e5" else "cross_encoder_raw_logit",
                        "minScore": threshold,
                        "calibration": selection_metrics(splits["calibration"], threshold),
                        "development": selection_metrics(splits["development"], threshold),
                    }
                )
        primary = select_primary(experiments)
        frozen = {
            "primaryExperimentId": primary,
            "protocol": PROTOCOL,
            "inputSha256": input_hashes,
            "models": {
                "e5": {"modelId": encoder.model_id, "revision": encoder.revision},
                "cross_encoder": {"modelId": reranker.model_id, "revision": reranker.revision},
            },
            "policies": [
                {k: v for k, v in e.items() if k not in ("calibration", "development")} for e in experiments
            ],
        }
        frozen_path = args.output.with_name("reranker-frozen-selection.json")
        frozen_path.write_text(json.dumps(frozen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        frozen_hash = digest(frozen_path)
        print(json.dumps({"primaryFrozen": primary, "infeasible": infeasible}), flush=True)
        # First load and inference of the fresh test happen only after model/criteria have been frozen.
        final = json.loads((ROOT / "evaluation/reranker-test.json").read_text(encoding="utf-8"))["scenarios"]
        old_families = {s["familyId"] for s in calibration["scenarios"] + development["scenarios"]}
        assert not (old_families & {s["familyId"] for s in final})
        scored["e5"]["finalTest"] = score_split(encoder, catalog, final)
        scored["cross_encoder"]["finalTest"] = score_reranker(reranker, catalog, final)
        for e in experiments:
            e["finalTest"] = selection_metrics(scored[e["model"]]["finalTest"], e["minScore"])
        assert digest(frozen_path) == frozen_hash
        print("Final test evaluated once; benchmarking all 15 candidates", flush=True)
        performance = benchmark(encoder, reranker, catalog, calibration["scenarios"][0])
        report = {
            "primaryExperimentId": primary,
            "frozenSelectionSha256": frozen_hash,
            "protocol": frozen,
            "experiments": experiments,
            "infeasibleOnCalibration": infeasible,
            "rankingMetrics": {
                model: {split: ranking_metrics(rows) for split, rows in splits.items()}
                for model, splits in scored.items()
            },
            "searchesCalibrationOnly": searches,
            "scores": scored,
            "performance": {
                **performance,
                "sampledPeakRssBytesBothModels": peak[0],
                "currentRssBytesBothModels": process.memory_info().rss,
                "e5LoadSeconds": e5_load,
                "rerankerLoadSeconds": ce_load,
                "platform": platform.platform(),
                "python": platform.python_version(),
                "logicalCpuCount": psutil.cpu_count(),
            },
            "notice": "Research experiment only. Current API/model/production threshold unchanged. Synthetic proposed labels. CrossEncoder logits are not cosine similarity or approval probabilities.",
        }
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "primary": primary,
                    "finalTest": [
                        {
                            "id": e["id"],
                            **{
                                k: v
                                for k, v in e["finalTest"].items()
                                if k
                                in (
                                    "precision",
                                    "recall",
                                    "f1",
                                    "f0.5",
                                    "coverage",
                                    "noRelevantRejectionRate",
                                )
                            },
                        }
                        for e in experiments
                    ],
                    "performance": report["performance"],
                }
            ),
            flush=True,
        )
    finally:
        stop.set()
        monitor.join()


if __name__ == "__main__":
    main()
