import json
from types import SimpleNamespace

import numpy as np
import pytest
from conftest import ROOT

from scripts.reranker_experiment import (
    LocalReranker,
    choose_policies,
    ranking_metrics,
    select_primary,
    selection_metrics,
)


def example_rows():
    return [
        {
            "id": "controlled",
            "relevant": ["a", "c"],
            "ranking": [
                {"code": "a", "score": 0.9},
                {"code": "b", "score": 0.8},
                {"code": "c", "score": 0.7},
            ],
        }
    ]


def test_f1_and_precision_focused_objectives_make_different_selections():
    rows = example_rows()
    policies, _ = choose_policies(rows)
    f1 = selection_metrics(rows, policies["f1"]["minScore"])
    f05 = selection_metrics(rows, policies["f0.5"]["minScore"])
    assert f1["recall"] == 1 and f1["precision"] == pytest.approx(2 / 3)
    assert f05["precision"] == 1 and f05["recall"] == 0.5
    assert f05["f0.5"] > f1["f0.5"]
    assert policies["precision_at_recall_50"]["precision"] == 1


def test_unattainable_precision_constraint_is_not_silently_relaxed():
    rows = [
        {
            "id": "impossible",
            "relevant": ["good"],
            "ranking": [{"code": "bad", "score": 5.0}, {"code": "good", "score": 4.0}],
        }
    ]
    policies, _ = choose_policies(rows)
    assert policies["recall_at_precision_80"] is None
    assert selection_metrics(rows, 4.5)["recall"] == 0
    assert selection_metrics(rows, 3)["precision"] == 0.5
    assert selection_metrics(rows, 6)["coverage"] == 0


def test_primary_selection_never_uses_final_test_results():
    def metrics(f05):
        return {"f0.5": f05, "precision": 0.9, "f1": 0.5, "recall": 0.5, "coverage": 0.5}

    experiments = [
        {"id": "dev-winner", "development": metrics(0.8), "finalTest": metrics(0.1)},
        {"id": "test-winner", "development": metrics(0.7), "finalTest": metrics(1)},
    ]
    assert select_primary(experiments) == "dev-winner"
    for e in experiments:
        e["development"]["coverage"] = 0
    with pytest.raises(ValueError, match="No experiment"):
        select_primary(experiments)


def test_ranking_metrics_ignore_no_relevant_cases():
    rows = example_rows() + [{"id": "none", "relevant": [], "ranking": [{"code": "b", "score": 100}]}]
    result = ranking_metrics(rows)
    assert result["mrr"] == 1 and result["rankEvaluatedCount"] == 1
    assert 0 < result["ndcgAt3"] < 1


def test_fresh_final_test_has_no_profile_or_family_overlap():
    final = json.loads((ROOT / "evaluation/reranker-test.json").read_text(encoding="utf-8"))["scenarios"]
    old = []
    for name in ("calibration.json", "holdout.json"):
        old += json.loads((ROOT / "evaluation" / name).read_text(encoding="utf-8"))["scenarios"]
    assert len(final) == 90 and len({s["familyId"] for s in final}) == 30
    assert not ({s["familyId"] for s in old} & {s["familyId"] for s in final})

    def canonical(s):
        return json.dumps(s["profile"], sort_keys=True, ensure_ascii=False)

    assert not ({canonical(s) for s in old} & {canonical(s) for s in final})
    assert all(s["labelStatus"] == "SYNTHETIC_PROPOSED" for s in final)


def test_reranker_rejects_long_pairs_and_nonfinite_logits():
    encoder = LocalReranker.__new__(LocalReranker)
    encoder.model = SimpleNamespace(
        tokenizer=lambda *a, **k: {"input_ids": [[0] * 513]}, predict=lambda *a, **k: np.array([0.2])
    )
    with pytest.raises(ValueError, match="512 tokens"):
        encoder.predict([("query", "passage")])
    encoder.model.tokenizer = lambda *a, **k: {"input_ids": [[0, 1]]}
    encoder.model.predict = lambda *a, **k: np.array([np.nan])
    with pytest.raises(ValueError, match="Invalid CrossEncoder"):
        encoder.predict([("query", "passage")])
    assert encoder.predict([]).shape == (0,)
