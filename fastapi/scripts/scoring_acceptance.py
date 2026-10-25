"""Offline-package HTTP acceptance and latency under concurrent E5 traffic."""

import argparse
import copy
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:18082")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    environment = dict(os.environ)
    if args.env_file:
        environment.update(
            line.split("=", 1) for line in args.env_file.read_text().splitlines() if "=" in line
        )
    key = environment["ML_INTERNAL_API_KEY"]
    opener = build_opener(ProxyHandler({}))
    root = Path(__file__).resolve().parents[1]
    payload = dict(
        schemaVersion="sba-scoring-1",
        requestId=str(uuid4()),
        loanAmountUsd="3333.33",
        termMonths=12,
        initialInterestRatePct="28.00000",
        interestRateType="FIXED",
        isRevolving=False,
        hasCollateral=False,
        businessType="CORPORATION",
        businessAgeCategory="Existing, 5 or more years",
        naicsCode="445110",
    )
    ranking = json.loads((root / "examples/java-rank-request.json").read_text(encoding="utf-8"))

    def call(path, body=None, header="Authorization"):
        headers = {
            header: "Bearer " + key if header == "Authorization" else key,
            "Content-Type": "application/json",
        }
        request = Request(
            args.url + path, data=json.dumps(body).encode() if body is not None else None, headers=headers
        )
        start = time.perf_counter()
        with opener.open(request, timeout=15) as response:
            return json.load(response), (time.perf_counter() - start) * 1000

    assert call("/health/ready")[0]["status"] == "ready"
    assert call("/api/v1/scoring/ready")[0]["status"] == "ready"
    info = call("/api/v1/scoring/model-info")[0]
    rank_before = call("/api/v1/recommendations/rank-java", ranking)[0]

    def score(_):
        body = copy.deepcopy(payload)
        body["requestId"] = str(uuid4())
        result, duration = call("/api/v1/scoring/evaluate", body)
        assert result["requestId"] == body["requestId"]
        assert result["modelVersion"] == info["modelVersion"]
        assert result["featureVersion"] == "sba-features-1"
        assert result["domainStatus"] == "EXTRAPOLATION"
        assert {"RATE_OUT_OF_RANGE", "SBA_US_TO_RU_DEMO", "TERM_HISTORY_UNCONFIRMED"} <= set(
            result["warnings"]
        )
        expected = int(
            ((1 - Decimal(str(result["sbaDefaultProbability"]))) * 100).quantize(
                Decimal(1), rounding=ROUND_HALF_UP
            )
        )
        assert result["score"] == expected
        return duration

    for index in range(10):
        score(index)
    single = [score(index) for index in range(50)]
    with ThreadPoolExecutor(max_workers=4) as executor:
        burst = list(executor.map(score, range(100)))
    with ThreadPoolExecutor(max_workers=5) as executor:
        mixed = []
        for _index in range(15):
            future = executor.submit(call, "/api/v1/recommendations/rank-java", ranking)
            mixed.extend(executor.map(score, range(4)))
            assert future.result()[0] == rank_before
    rank_after = call("/api/v1/recommendations/rank-java", ranking)[0]
    assert rank_before == rank_after

    def summary(values):
        return {
            "requests": len(values),
            "p50Ms": float(np.percentile(values, 50)),
            "p95Ms": float(np.percentile(values, 95)),
            "p99Ms": float(np.percentile(values, 99)),
            "maxMs": max(values),
        }

    result = {
        "scoring": info,
        "single": summary(single),
        "concurrent": summary(burst),
        "withE5": summary(mixed),
        "scoringConcurrency": 4,
        "mixedConcurrency": "four scoring requests plus one E5 request",
        "rankingUnchanged": True,
        "rankingMetadata": rank_after["metadata"],
        "isDemo": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
