from types import SimpleNamespace

import numpy as np
import pytest

from scripts import verify_model


def test_unresolved_lfs_pointer_and_missing_weights_are_actionable(tmp_path):
    with pytest.raises(ValueError, match="git lfs"):
        verify_model.check_lfs_download(tmp_path)
    (tmp_path / "model.safetensors").write_bytes(
        b"version https://git-lfs.github.com/spec/v1\noid sha256:" + b"a" * 64 + b"\nsize 100\n"
    )
    with pytest.raises(ValueError, match="still a Git LFS pointer"):
        verify_model.check_lfs_download(tmp_path)


def test_package_checker_uses_runtime_identity_and_optional_encoder(tmp_path, monkeypatch):
    (tmp_path / "model.safetensors").write_bytes(b"controlled test asset")
    lock = {"modelId": "local/test", "revision": "a" * 64, "baseModelId": "base", "baseRevision": "b" * 40}
    manifest = {
        "localModelId": lock["modelId"],
        "artifactSha256": lock["revision"],
        "baseModelId": "base",
        "baseRevision": lock["baseRevision"],
        "dimension": 384,
        "maxSeqLength": 512,
        "checksums": {"model.safetensors": "x"},
    }
    monkeypatch.setattr(verify_model, "locked_model", lambda _: lock)
    monkeypatch.setattr(verify_model, "verify_finetuned_manifest", lambda *_: manifest)
    monkeypatch.setattr(
        verify_model, "Settings", lambda **_: SimpleNamespace(recommendation_max_cosine_distance=0.5)
    )
    calls = []
    monkeypatch.setattr(
        verify_model,
        "SentenceEncoder",
        lambda _: (
            calls.append(True)
            or SimpleNamespace(
                token_lengths=lambda _: [10, 12], encode=lambda _: np.ones((2, 384), dtype=np.float32)
            )
        ),
    )
    assert verify_model.verify_package(tmp_path)["smoke"] == "not_requested" and not calls
    assert verify_model.verify_package(tmp_path, smoke=True)["smoke"]["shape"] == [2, 384]
    assert len(calls) == 1
    manifest["baseRevision"] = "c" * 40
    with pytest.raises(ValueError, match="metadata"):
        verify_model.verify_package(tmp_path)
