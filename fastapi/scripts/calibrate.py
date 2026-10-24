"""Select a threshold on calibration only, freeze it, then evaluate a disjoint holdout."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np

from app.core.config import ROOT, VERSIONS, Settings
from app.schemas.requests import Product, Profile
from app.services.encoder import SentenceEncoder
from app.services.text_builder import build_passage, build_query


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_data(directory=ROOT / "evaluation"):
    calibration = json.loads((directory / "calibration.json").read_text(encoding="utf-8"))
    holdout = json.loads((directory / "holdout.json").read_text(encoding="utf-8"))
    products = json.loads((directory / "backend-products.json").read_text(encoding="utf-8"))["products"]
    assert (
        calibration["productsSha256"]
        == holdout["productsSha256"]
        == digest(directory / "backend-products.json")
    )
    assert not (
        {s["familyId"] for s in calibration["scenarios"]} & {s["familyId"] for s in holdout["scenarios"]}
    )

    def encode_profile(s):
        return json.dumps(s["profile"], sort_keys=True, ensure_ascii=False)

    assert not (
        {encode_profile(s) for s in calibration["scenarios"]}
        & {encode_profile(s) for s in holdout["scenarios"]}
    )
    catalog = {}
    for p in products:
        raw = {k: v for k, v in p.items() if k not in ("code", "synthetic")}
        raw["targetSectors"] = ["TRANSPORT" if x == "LOGISTICS" else x for x in raw["targetSectors"]]
        catalog[p["code"]] = Product.model_validate(raw)
    for split in (calibration, holdout):
        assert len({s["id"] for s in split["scenarios"]}) == len(split["scenarios"])
        for s in split["scenarios"]:
            assert set(s["relevantProductCodes"]) <= set(s["candidateProductCodes"]) <= set(catalog)
            assert len(set(s["candidateProductCodes"])) == len(s["candidateProductCodes"])
    return catalog, calibration, holdout


def score_split(encoder, catalog, scenarios):
    passages = {code: build_passage(p) for code, p in catalog.items()}
    queries = []
    for s in scenarios:
        raw = json.loads(json.dumps(s["profile"]))
        if raw["business"]["sector"] == "LOGISTICS":
            raw["business"]["sector"] = "TRANSPORT"
        queries.append(build_query(Profile.model_validate(raw)))
    texts = list(dict.fromkeys([*passages.values(), *queries]))
    assert max(encoder.token_lengths(texts)) <= 512
    vectors = dict(zip(texts, encoder.encode(texts), strict=True))
    rows = []
    for s, q in zip(scenarios, queries, strict=True):
        codes = s["candidateProductCodes"]
        scores = np.stack([vectors[passages[c]] for c in codes]) @ vectors[q]
        order = sorted(range(len(codes)), key=lambda i: (-float(scores[i]), catalog[codes[i]].id))
        rows.append(
            {
                "id": s["id"],
                "familyId": s["familyId"],
                "intent": s["intent"],
                "relevant": s["relevantProductCodes"],
                "ranking": [{"code": codes[i], "score": float(np.clip(scores[i], -1, 1))} for i in order],
            }
        )
    return rows


def metrics(rows, max_distance):
    tp = fp = fn = abstained = no_relevant = rejected_none = 0
    counts = Counter()
    cases = []
    for row in rows:
        selected = [p["code"] for p in row["ranking"][:3] if 1 - p["score"] <= max_distance]
        positive, predicted = set(row["relevant"]), set(selected)
        tp += len(positive & predicted)
        fp += len(predicted - positive)
        fn += len(positive - predicted)
        abstained += not selected
        no_relevant += not positive
        rejected_none += not positive and not selected
        counts[len(selected)] += 1
        cases.append(
            {
                "id": row["id"],
                "recommended": selected,
                "relevant": row["relevant"],
                "falsePositives": sorted(predicted - positive),
                "missed": sorted(positive - predicted),
            }
        )
    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    return {
        "precision": precision,
        "recall": recall,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "scenarioCount": len(rows),
        "abstentionCount": abstained,
        "recommendationCountHistogram": {str(k): counts[k] for k in range(4)},
        "noRelevantCount": no_relevant,
        "noRelevantAbstentionCount": rejected_none,
        "cases": cases,
    }


def choose_threshold(rows):
    distances = sorted({1 - p["score"] for r in rows for p in r["ranking"][:3]})
    candidates = sorted(
        {0.0, 2.0, *(round((a + b) / 2, 12) for a, b in zip(distances, distances[1:], strict=False))}
    )
    # Objective was fixed in the dataset before inference. No holdout results enter this function.
    best = max(candidates, key=lambda d: (metrics(rows, d)["f1"], metrics(rows, d)["precision"], -d))
    return best, [
        {
            "maxCosineDistance": d,
            **{k: v for k, v in metrics(rows, d).items() if k in ("precision", "recall", "f1")},
        }
        for d in candidates
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/calibration.json")
    parser.add_argument("--policy-output", type=Path, default=ROOT / "config/selection-policy.json")
    args = parser.parse_args()
    catalog, calibration, holdout = load_data()
    settings = Settings(recommendation_max_cosine_distance=None)
    encoder = SentenceEncoder(settings)
    cal_rows = score_split(encoder, catalog, calibration["scenarios"])
    threshold, search = choose_threshold(cal_rows)
    policy = {
        "policyVersion": "top_k_cosine_distance_v1",
        "modelId": encoder.model_id,
        "modelRevision": encoder.revision,
        "templates": VERSIONS,
        "maxCosineDistance": threshold,
        "labelStatus": calibration["labelStatus"],
        "status": "SYNTHETIC_CALIBRATION_PROVISIONAL",
        "objective": calibration["objective"],
        "calibrationSha256": digest(ROOT / "evaluation/calibration.json"),
        "productsSha256": digest(ROOT / "evaluation/backend-products.json"),
    }
    args.policy_output.parent.mkdir(parents=True, exist_ok=True)
    args.policy_output.write_text(json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    frozen_policy = digest(args.policy_output)
    print(json.dumps({"frozenMaxCosineDistance": threshold, "policySha256": frozen_policy}), flush=True)
    # Holdout inference starts only after the threshold artifact has been saved.
    test_rows = score_split(encoder, catalog, holdout["scenarios"])
    assert digest(args.policy_output) == frozen_policy
    report = {
        "policy": policy,
        "policySha256": frozen_policy,
        "holdoutSha256": digest(ROOT / "evaluation/holdout.json"),
        "calibration": metrics(cal_rows, threshold),
        "holdout": metrics(test_rows, threshold),
        "searchCalibrationOnly": search,
        "calibrationScores": cal_rows,
        "holdoutScores": test_rows,
        "notice": "Synthetic proposed labels, not expert-confirmed. Holdout has not been used to choose the threshold. Metrics describe this synthetic distribution only.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                split: {k: v for k, v in report[split].items() if k != "cases"}
                for split in ("calibration", "holdout")
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
