import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import boto3
import pytest

from app.core.config import Settings
from app.services.model_source import resolve_model_path


def fixture_package(tmp_path, monkeypatch, variant="finetuned", mutation=None):
    assets = {"config.json": b"{}", "model.safetensors": b"controlled-weights"}
    files = {name: hashlib.sha256(data).hexdigest() for name, data in assets.items()}
    if mutation == "traversal":
        files["../escape"] = files.pop("config.json")
    fingerprint = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    settings = Settings(
        model_path="s3://bucket/prefix",
        model_variant=variant,
        hf_cache_dir=tmp_path,
        aws_access_key_id="CONTROLLED_KEY",
        aws_secret_access_key="CONTROLLED_SECRET",
        environment="test",
        ml_internal_api_key="test",
    )
    manifest = {
        "checksums": files,
        "artifactSha256": fingerprint,
        "modelId": settings.model_id,
        "revision": settings.model_revision,
    }
    if variant == "finetuned":
        settings.model_revision = fingerprint
    if mutation == "identity":
        manifest["artifactSha256"] = "0" * 64
        manifest["revision"] = "0" * 40
    raw = json.dumps(manifest).encode() if mutation != "json" else b"invalid"
    if mutation == "oversized":
        raw = b"x" * 1048577
    get = Mock(side_effect=lambda **_: {"Body": io.BytesIO(raw)})

    def download(bucket, key, target, **kwargs):
        assert bucket == "bucket" and kwargs["Config"].max_concurrency == 2
        Path(target).write_bytes(b"corrupt" if mutation == "checksum" else assets[key.split("/")[-1]])

    client = SimpleNamespace(get_object=get, download_file=Mock(side_effect=download))
    factory = Mock(return_value=client)
    if mutation == "client":
        factory.side_effect = RuntimeError("PRIVATE_AWS_CREDENTIAL")
    monkeypatch.setattr(boto3, "client", factory)
    return settings, client, factory


@pytest.mark.parametrize("variant", ["finetuned", "base"])
def test_s3_download_checks_files_and_reuses_cache(tmp_path, monkeypatch, variant):
    settings, client, factory = fixture_package(tmp_path, monkeypatch, variant)
    folder = resolve_model_path(settings)
    assert (folder / "model.safetensors").read_bytes() == b"controlled-weights"
    assert client.download_file.call_count == 2
    assert factory.call_args.kwargs["aws_secret_access_key"] == "CONTROLLED_SECRET"
    assert "CONTROLLED_SECRET" not in repr(settings) + str(settings.model_dump())
    factory.side_effect = RuntimeError("must not connect")
    assert resolve_model_path(settings) == folder and factory.call_count == 1


@pytest.mark.parametrize("mutation", ["json", "identity", "traversal", "checksum", "oversized", "client"])
def test_s3_bad_objects_never_publish_cache_or_expose_credentials(tmp_path, monkeypatch, mutation):
    settings, client, factory = fixture_package(tmp_path, monkeypatch, mutation=mutation)
    with pytest.raises(ValueError, match="S3 model download failed") as error:
        resolve_model_path(settings)
    assert "PRIVATE_AWS" not in str(error.value)
    assert not list((tmp_path / "s3-packages").iterdir())
