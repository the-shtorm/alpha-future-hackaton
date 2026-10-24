import hashlib
import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from app.core.config import MODEL_ID
from app.services.encoder import SentenceEncoder, verify_manifest


@pytest.fixture
def model_dir(tmp_path):
    files = {
        "config.json": "{}",
        "modules.json": "[]",
        "1_Pooling/config.json": "{}",
        "tokenizer_config.json": "{}",
        "model.safetensors": "weights",
    }
    manifest = {"modelId": MODEL_ID, "revision": "a" * 40, "checksums": {}}
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        manifest["checksums"][name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    return tmp_path


def test_valid_manifest_and_revision(model_dir):
    assert verify_manifest(model_dir)["revision"] == "a" * 40
    with pytest.raises(ValueError, match="differs"):
        verify_manifest(model_dir, "b" * 40)


@pytest.mark.parametrize("mutation", ["identity", "sha", "incomplete", "extra", "checksum", "unsafe"])
def test_manifest_corruption(model_dir, mutation):
    path = model_dir / "manifest.json"
    manifest = json.loads(path.read_text())
    if mutation == "identity":
        manifest["modelId"] = "bad"
    elif mutation == "sha":
        manifest["revision"] = "main"
    elif mutation == "incomplete":
        del manifest["checksums"]["config.json"]
    elif mutation == "extra":
        (model_dir / "extra.txt").write_text("extra")
    elif mutation == "checksum":
        (model_dir / "config.json").write_text("changed")
    else:
        file = model_dir / "execute.py"
        file.write_text("unsafe")
        manifest["checksums"][file.name] = hashlib.sha256(file.read_bytes()).hexdigest()
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        verify_manifest(model_dir)


@pytest.mark.parametrize("threads", [1, 2])
def test_encoder_local_only_arguments_and_tokens(model_dir, settings, monkeypatch, threads):
    torch = SimpleNamespace(
        float32="float32",
        set_num_threads=Mock(),
        get_num_interop_threads=lambda: threads,
        set_num_interop_threads=Mock(),
    )
    model = Mock()
    model.get_sentence_embedding_dimension.return_value = 384
    model.tokenizer.return_value = {"input_ids": [[1, 2, 3], [4, 5]]}
    vectors = np.zeros((2, 384), dtype=np.float32)
    vectors[:, 0] = 1
    model.encode.return_value = vectors
    factory = Mock(return_value=model)
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=factory))
    settings.model_local_path = model_dir
    settings.model_revision = "a" * 40
    encoder = SentenceEncoder(settings)
    assert encoder.token_lengths(["query: a", "passage: b"]) == [3, 2]
    assert encoder.encode(["query: a", "passage: b"]).shape == (2, 384)
    assert factory.call_args.kwargs["local_files_only"] is True
    assert factory.call_args.kwargs["trust_remote_code"] is False
    assert model.encode.call_args.kwargs["prompt"] == ""
    assert model.default_prompt_name is None and model.max_seq_length == 512
    assert torch.set_num_interop_threads.call_count == int(threads != 1)
    model.get_sentence_embedding_dimension.return_value = 42
    with pytest.raises(ValueError, match="dimension"):
        SentenceEncoder(settings)
