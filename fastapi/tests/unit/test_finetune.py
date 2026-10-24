from types import SimpleNamespace

import numpy as np
import pytest

from scripts.calibrate import load_data
from scripts.finetune_utils import (
    choose_f05_distance,
    mine_pairs,
    query_text,
    validate_split_isolation,
    verify_finetuned_manifest,
    write_model_manifest,
)


def test_training_profiles_are_separate_from_all_evaluation_splits():
    groups = validate_split_isolation()
    assert {k: len(v) for k, v in groups.items()} == {
        "train": 1500,
        "calibration": 180,
        "development": 180,
        "final": 90,
    }
    assert len({s["familyId"] for s in groups["train"]}) == 300
    assert all(s["labelStatus"] == "SYNTHETIC_PROPOSED" for s in groups["train"])


def test_hard_negative_mining_never_uses_known_positives_as_negatives():
    catalog, _, _ = load_data()
    scenarios = validate_split_isolation()["train"][:3]

    def encode(texts, **kwargs):
        values = np.zeros((len(texts), 384), dtype=np.float32)
        values[:, 0] = 1
        return values

    model = SimpleNamespace(
        encode=encode, tokenizer=lambda texts, **kwargs: {"input_ids": [[0, 1] for _ in texts]}
    )
    pairs, audit = mine_pairs(model, catalog, scenarios)
    assert len(audit) == len(scenarios)
    for row in audit:
        assert not set(row["positiveCodes"]) & set(row["hardNegativeCodes"] + row["otherNegativeCodes"])
    assert {p["label"] for p in pairs} == {0.0, 1.0}
    assert all(p["query"].count("query:") == p["passage"].count("passage:") == 1 for p in pairs)
    assert pairs == mine_pairs(model, catalog, scenarios)[0]


def test_precision_focused_threshold_uses_only_given_calibration_rows():
    rows = [
        {
            "id": "control",
            "relevant": ["a", "c"],
            "ranking": [
                {"code": "a", "score": 0.9},
                {"code": "b", "score": 0.8},
                {"code": "c", "score": 0.7},
            ],
        }
    ]
    assert 0.1 <= choose_f05_distance(rows) < 0.2


def test_export_manifest_detects_corruption_and_unexpected_files(tmp_path):
    (tmp_path / "model.safetensors").write_bytes(b"controlled-weights")
    (tmp_path / "config.json").write_text("{}")
    manifest = write_model_manifest(tmp_path, {"localModelId": "local/test"})
    assert verify_finetuned_manifest(tmp_path)["artifactSha256"] == manifest["artifactSha256"]
    (tmp_path / "config.json").write_text('{"changed":true}')
    with pytest.raises(ValueError, match="checksum"):
        verify_finetuned_manifest(tmp_path)
    (tmp_path / "unsafe.py").write_text("pass")
    with pytest.raises(ValueError, match="file set"):
        verify_finetuned_manifest(tmp_path)


def test_logistics_uses_same_production_query_prefix_and_labels():
    text = query_text(
        {
            "business": {"sector": "LOGISTICS"},
            "request": {"purpose": "WORKING_CAPITAL", "usageMode": "ONE_TIME"},
            "security": {"collateralReady": "UNKNOWN", "guarantorReady": "UNKNOWN"},
        }
    )
    assert text.startswith("query: ") and "транспорт и логистика" in text
