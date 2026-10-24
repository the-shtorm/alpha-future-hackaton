"""Offline CPU smoke and benchmark for the exported candidate, without changing the API model."""

import argparse
import json
import time
from pathlib import Path

import numpy as np
import psutil
import torch

from app.core.config import ROOT
from app.schemas.requests import RankRequest
from app.services.ranker import Ranker
from scripts.calibrate import load_data
from scripts.evaluate_finetune import load_candidate
from scripts.finetune_utils import ModelEncoder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=ROOT / "models/e5-credit-finetune-v1/final")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    start = time.perf_counter()
    model, manifest = load_candidate(args.model)
    load_seconds = time.perf_counter() - start
    encoder = ModelEncoder(model, batch_size=4)
    encoder.model_id, encoder.revision = manifest["localModelId"], manifest["artifactSha256"][:40]
    vectors = encoder.encode(
        [
            "query: Нужны деньги на производственное оборудование.",
            "passage: Кредит на приобретение оборудования.",
        ]
    )
    assert vectors.shape == (2, 384) and np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-4)
    catalog, calibration, _ = load_data()
    profile = calibration["scenarios"][0]["profile"]
    request = RankRequest.model_validate(
        {
            "requestId": "fine-tuned-cpu-benchmark",
            "profile": profile,
            "topK": 3,
            "candidates": [
                {"product": p.model_dump(), "eligibilityStatus": "ELIGIBLE", "pendingConditions": []}
                for p in catalog.values()
            ],
        }
    )
    frozen = json.loads((ROOT / "reports/e5-finetune-frozen-policies.json").read_text(encoding="utf-8"))
    ranker = Ranker(encoder, max_cosine_distance=frozen["thresholds"]["fineTuned"])
    start = time.perf_counter()
    ranker.rank(request)
    cold = (time.perf_counter() - start) * 1000
    times = []
    for _ in range(12):
        start = time.perf_counter()
        response = ranker.rank(request)
        times.append((time.perf_counter() - start) * 1000)
        assert len(response.results) == 15 and sum(p.isRecommended for p in response.results) <= 3
    result = {
        "passed": True,
        "modelId": encoder.model_id,
        "artifactSha256": manifest["artifactSha256"],
        "device": "cpu",
        "dimension": 384,
        "candidateCount": 15,
        "loadSeconds": load_seconds,
        "coldRankMs": cold,
        "warmP50Ms": float(np.percentile(times, 50)),
        "warmP95Ms": float(np.percentile(times, 95)),
        "currentRssBytes": psutil.Process().memory_info().rss,
        "cgroupMemory": {
            name: Path("/sys/fs/cgroup", name).read_text().strip()
            for name in ("memory.current", "memory.peak", "memory.max")
        },
        "transport": "ranker/model only, no HTTP or Java",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
