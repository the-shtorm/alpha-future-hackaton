import json
import os
from pathlib import Path

import numpy as np
import pytest
from conftest import ROOT
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.encoder import SentenceEncoder

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("RUN_REAL_MODEL_TESTS"), reason="Set RUN_REAL_MODEL_TESTS=1 with prepared local weights"
    ),
]


@pytest.mark.parametrize(
    "variant",
    [
        "base",
        pytest.param(
            "finetuned",
            marks=pytest.mark.skipif(
                not os.getenv("RUN_FINETUNED_MODEL_TESTS"),
                reason="Set RUN_FINETUNED_MODEL_TESTS=1 with saved checkpoint",
            ),
        ),
    ],
)
def test_real_offline_encoder_and_http(payload, monkeypatch, variant):
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    settings = Settings(
        model_variant=variant,
        environment="test",
        ml_internal_api_key="integration-key",
        model_local_path=Path(
            os.getenv("FINETUNED_MODEL_LOCAL_PATH", "models/e5-credit-finetune-v1/final")
            if variant == "finetuned"
            else os.getenv("MODEL_LOCAL_PATH", "models/multilingual-e5-small")
        ),
    )
    encoder = SentenceEncoder(settings)
    texts = ["query: Нужны деньги на оборудование.", "passage: Покупка станка для производства."]
    assert max(encoder.token_lengths(texts)) <= 512
    first = encoder.encode(texts)
    second = encoder.encode(texts)
    assert first.shape == (2, 384)
    assert np.isfinite(first).all() and np.allclose(np.linalg.norm(first, axis=1), 1, atol=1e-4)
    assert np.allclose(first, second, atol=1e-6)
    with TestClient(create_app(settings, lambda _: encoder)) as client:
        response = client.post(
            "/api/v1/recommendations/rank", json=payload, headers={"X-Internal-API-Key": "integration-key"}
        )
        assert response.status_code == 200
        assert response.json()["metadata"]["modelId"] == settings.model_id
        assert response.json()["metadata"]["modelRevision"] == settings.model_revision
        assert response.json()["metadata"]["maxCosineDistance"] == settings.recommendation_max_cosine_distance
        assert len(response.json()["results"]) == len(payload["candidates"])
        java = json.loads((ROOT / "examples/java-rank-request.json").read_text(encoding="utf-8"))
        java_response = client.post(
            "/api/v1/recommendations/rank-java",
            json=java,
            headers={"Authorization": "Bearer integration-key"},
        )
        assert java_response.status_code == 200, java_response.text
        assert set(java_response.json()["metadata"]) == {
            "model",
            "modelVersion",
            "queryTemplateVersion",
            "passageTemplateVersion",
        }
        original_conditions = {c["productId"]: c["pendingConditions"] for c in java["candidates"]}
        for result in java_response.json()["results"]:
            assert result["pendingConditions"] == original_conditions[result["productId"]]
        # High token count can fit within the character limit (many uncommon Unicode symbols).
        payload["profile"]["request"]["description"] = "龘 " * 250
        response = client.post(
            "/api/v1/recommendations/rank", json=payload, headers={"X-Internal-API-Key": "integration-key"}
        )
        assert response.status_code == 422 and response.json()["error"]["code"] == "TEXT_TOO_LONG"
