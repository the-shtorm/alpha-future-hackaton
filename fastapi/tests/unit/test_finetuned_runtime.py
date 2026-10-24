import hashlib
import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core import config
from app.core.config import Settings, locked_model
from app.services.encoder import SentenceEncoder, verify_finetuned_manifest
from scripts.finetune_utils import write_model_manifest


def test_default_runtime_selects_saved_checkpoint_and_matching_threshold():
    settings = Settings(environment="test", ml_internal_api_key="test")
    lock = locked_model("finetuned")
    assert settings.model_variant == "finetuned"
    assert settings.model_id == lock["modelId"] == "local/e5-credit-finetune-v1"
    assert settings.model_revision == lock["revision"]
    assert settings.model_local_path == config.ROOT / "models/e5-credit-finetune-v1/final"
    assert settings.recommendation_max_cosine_distance == 0.5237781852483749
    assert (
        Settings(
            environment="test", ml_internal_api_key="test", recommendation_max_cosine_distance=None
        ).recommendation_max_cosine_distance
        is None
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"model_id": "intfloat/multilingual-e5-small"},
        {"model_revision": "614241f622f53c4eeff9890bdc4f31cfecc418b3"},
        {"model_variant": "unknown"},
    ],
)
def test_runtime_rejects_mixed_model_identity(changes):
    with pytest.raises(ValueError):
        Settings(environment="test", ml_internal_api_key="test", **changes)


@pytest.mark.parametrize("distance", [True, -0.1, 2.1, float("nan"), "0.4"])
def test_invalid_policy_distance_fails_closed(tmp_path, monkeypatch, distance):
    lock = locked_model("finetuned")
    policy = json.loads((config.ROOT / "config/finetuned-selection-policy.json").read_text())
    policy["maxCosineDistance"] = distance
    (tmp_path / "config").mkdir()
    (tmp_path / "config/finetuned-model.lock.json").write_text(json.dumps(lock))
    (tmp_path / "config/finetuned-selection-policy.json").write_text(json.dumps(policy))
    monkeypatch.setattr(config, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="cosine distance"):
        config.calibrated_distance("finetuned")


def test_finetuned_encoder_verifies_identity_and_loads_local_cpu_assets(tmp_path, settings, monkeypatch):
    model_dir = tmp_path
    for name in ("config.json", "modules.json", "tokenizer_config.json", "model.safetensors"):
        (model_dir / name).write_text("{}")
    lock = locked_model("finetuned")
    metadata = {
        "localModelId": lock["modelId"],
        "baseModelId": lock["baseModelId"],
        "baseRevision": lock["baseRevision"],
        "dimension": 384,
        "maxSeqLength": 512,
    }
    manifest = write_model_manifest(model_dir, metadata)
    settings.model_variant = "finetuned"
    settings.model_id = lock["modelId"]
    settings.model_revision = manifest["artifactSha256"]
    settings.model_local_path = model_dir
    torch = SimpleNamespace(float32="float32", set_num_threads=Mock(), get_num_interop_threads=lambda: 1)
    model = Mock()
    model.get_sentence_embedding_dimension.return_value = 384
    factory = Mock(return_value=model)
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=factory))
    encoder = SentenceEncoder(settings)
    assert encoder.revision == manifest["artifactSha256"] and len(encoder.revision) == 64
    assert encoder.model_id == lock["modelId"]
    assert factory.call_args.kwargs == {
        "device": "cpu",
        "local_files_only": True,
        "trust_remote_code": False,
        "model_kwargs": {"torch_dtype": "float32"},
    }
    assert model.default_prompt_name is None and model.max_seq_length == 512
    with pytest.raises(ValueError, match="identity"):
        verify_finetuned_manifest(model_dir, "0" * 64)
    bad = dict(manifest, dimension=1)
    (model_dir / "finetune-manifest.json").write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="metadata"):
        SentenceEncoder(settings)
    bad = dict(manifest)
    unsafe = model_dir / "unsafe.py"
    unsafe.write_text("pass")
    bad["checksums"][unsafe.name] = hashlib.sha256(unsafe.read_bytes()).hexdigest()
    (model_dir / "finetune-manifest.json").write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="Unsafe"):
        verify_finetuned_manifest(model_dir)
