"""Shared, side-effect-free data/scoring helpers for the local E5 fine-tuning experiment."""

import hashlib
import json
import random

import numpy as np
from sklearn.metrics import average_precision_score

from app.core.config import ROOT
from app.schemas.requests import Profile
from app.services.encoder import validate_vectors
from app.services.encoder import verify_finetuned_manifest as verify_finetuned_manifest
from app.services.text_builder import build_passage, build_query
from scripts.calibrate import metrics, score_split


def query_text(profile):
    raw = json.loads(json.dumps(profile))
    if raw["business"]["sector"] == "LOGISTICS":
        raw["business"]["sector"] = "TRANSPORT"
    return build_query(Profile.model_validate(raw))


class ModelEncoder:
    def __init__(self, model, batch_size=16):
        self.model = model
        self.batch_size = batch_size

    def token_lengths(self, texts):
        return [
            len(x)
            for x in self.model.tokenizer(texts, add_special_tokens=True, truncation=False, padding=False)[
                "input_ids"
            ]
        ]

    def encode(self, texts):
        return validate_vectors(
            self.model.encode(
                texts,
                batch_size=self.batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
                prompt="",
            ),
            len(texts),
        )


def read_scenarios(name):
    return json.loads((ROOT / "evaluation" / name).read_text(encoding="utf-8"))["scenarios"]


def validate_split_isolation():
    groups = {
        "train": read_scenarios("finetune-train.json"),
        "calibration": read_scenarios("calibration.json"),
        "development": read_scenarios("holdout.json") + read_scenarios("reranker-test.json"),
        "final": read_scenarios("finetune-test.json"),
    }
    names = list(groups)
    for i, left in enumerate(names):
        for right in names[i + 1 :]:
            assert not ({s["familyId"] for s in groups[left]} & {s["familyId"] for s in groups[right]})
            assert not (
                {query_text(s["profile"]) for s in groups[left]}
                & {query_text(s["profile"]) for s in groups[right]}
            )
    return groups


def labeled_pairs(catalog, scenarios):
    rows = []
    for s in scenarios:
        query = query_text(s["profile"])
        relevant = set(s["relevantProductCodes"])
        for code in s["candidateProductCodes"]:
            rows.append(
                {"query": query, "passage": build_passage(catalog[code]), "label": float(code in relevant)}
            )
    return rows


def mine_pairs(model, catalog, scenarios, seed=20261024):
    encoder = ModelEncoder(model)
    codes = list(catalog)
    passages = [build_passage(catalog[c]) for c in codes]
    queries = [query_text(s["profile"]) for s in scenarios]
    assert max(encoder.token_lengths(queries + passages)) <= 512
    vectors = encoder.encode(passages)
    query_vectors = encoder.encode(queries)
    rng = random.Random(seed)
    result, audit = [], []
    for s, query, qv in zip(scenarios, queries, query_vectors, strict=True):
        eligible = set(s["candidateProductCodes"])
        positives = set(s["relevantProductCodes"])
        scores = vectors @ qv
        negatives = sorted(
            [c for c in eligible if c not in positives], key=lambda c: (-float(scores[codes.index(c)]), c)
        )
        hard = negatives[:4]
        easy = rng.sample(negatives[4:], min(2, len(negatives[4:])))
        for code in sorted(positives) + hard + easy:
            result.append(
                {"query": query, "passage": build_passage(catalog[code]), "label": float(code in positives)}
            )
        audit.append(
            {
                "id": s["id"],
                "familyId": s["familyId"],
                "positiveCodes": sorted(positives),
                "hardNegativeCodes": hard,
                "otherNegativeCodes": easy,
            }
        )
    rng.shuffle(result)
    return result, audit


def ranking_summary(rows):
    ndcg, mrr = [], []
    labels, scores = [], []
    for row in rows:
        positive = set(row["relevant"])
        gains = [int(p["code"] in positive) for p in row["ranking"]]
        labels.extend(gains)
        scores.extend(p["score"] for p in row["ranking"])
        if positive:
            dcg = sum(g / np.log2(i + 2) for i, g in enumerate(gains[:3]))
            ideal = sum(1 / np.log2(i + 2) for i in range(min(3, len(positive))))
            ndcg.append(dcg / ideal)
            mrr.append(next((1 / (i + 1) for i, g in enumerate(gains) if g), 0))
    return {
        "average_precision": float(average_precision_score(labels, scores)) if any(labels) else 0.0,
        "ndcg_at_3": float(np.mean(ndcg)) if ndcg else None,
        "mrr": float(np.mean(mrr)) if mrr else None,
    }


def choose_f05_distance(rows):
    distances = sorted({1 - p["score"] for row in rows for p in row["ranking"][:3]})
    candidates = [0.0, 2.0, *[(a + b) / 2 for a, b in zip(distances, distances[1:], strict=False)]]

    def objective(distance):
        m = metrics(rows, distance)
        tp, fp, fn = m["tp"], m["fp"], m["fn"]
        f05 = 1.25 * tp / (1.25 * tp + fp + 0.25 * fn) if tp + fp + fn else 0
        return f05, m["precision"], -distance

    return max(candidates, key=objective)


def score_model(model, catalog, scenarios):
    return score_split(ModelEncoder(model), catalog, scenarios)


def write_model_manifest(directory, metadata):
    files = sorted(p for p in directory.rglob("*") if p.is_file() and p.name != "finetune-manifest.json")
    checksums = {}
    for path in files:
        if path.suffix in (".bin", ".pkl", ".py", ".pickle"):
            raise ValueError("Export must contain only safe local model assets")
        with path.open("rb") as source:
            checksums[path.relative_to(directory).as_posix()] = hashlib.file_digest(
                source, "sha256"
            ).hexdigest()
    artifact_hash = hashlib.sha256(json.dumps(checksums, sort_keys=True).encode()).hexdigest()
    data = {**metadata, "artifactSha256": artifact_hash, "checksums": checksums}
    (directory / "finetune-manifest.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return data
