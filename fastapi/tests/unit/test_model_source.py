import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core.config import Settings
from app.services.model_source import materialize_cache_links, resolve_model_path


def hf_settings(**changes):
    return Settings(
        environment="test",
        ml_internal_api_key="test",
        model_source="hf",
        hf_model_id="org/model",
        hf_model_revision="a" * 40,
        **changes,
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"hf_model_id": None},
        {"hf_model_id": "https://example.com/model"},
        {"hf_model_revision": "main"},
        {"hf_model_revision": "a" * 39},
        {"hf_model_subfolder": "../outside"},
        {"hf_model_subfolder": "/absolute"},
        {"hf_model_subfolder": "model\\outside"},
    ],
)
def test_hf_configuration_requires_pinned_repo_and_safe_path(changes):
    values = dict(
        environment="test",
        ml_internal_api_key="test",
        model_source="hf",
        hf_model_id="org/model",
        hf_model_revision="a" * 40,
    )
    values.update(changes)
    with pytest.raises(ValueError):
        Settings(**values)


def test_local_source_does_not_import_hub(settings, monkeypatch):
    monkeypatch.setitem(sys.modules, "huggingface_hub", None)
    assert resolve_model_path(settings) == settings.model_local_path


@pytest.mark.parametrize("folder", ["model", ""])
def test_hf_download_is_pinned_authenticated_and_cacheable(tmp_path, monkeypatch, folder):
    directory = tmp_path / folder if folder else tmp_path
    directory.mkdir(exist_ok=True)
    download = Mock(return_value=str(tmp_path))
    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=download))
    settings = hf_settings(
        hf_model_subfolder=folder,
        hf_cache_dir=tmp_path / "cache",
        hf_local_files_only=True,
        hf_token="controlled-private-token",
    )
    assert resolve_model_path(settings) == directory
    kwargs = download.call_args.kwargs
    assert kwargs["revision"] == "a" * 40 and kwargs["repo_id"] == "org/model"
    assert kwargs["token"] == "controlled-private-token" and kwargs["local_files_only"] is True
    assert kwargs["allow_patterns"] == (["model/**"] if folder else None)
    assert kwargs["cache_dir"] == tmp_path / "cache"
    assert "controlled-private-token" not in repr(settings) + str(settings.model_dump())


def test_hf_errors_are_sanitized_and_never_fall_back_to_local(tmp_path, monkeypatch):
    download = Mock(side_effect=RuntimeError("PRIVATE_TOKEN_AND_LOCAL_PATH"))
    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=download))
    with pytest.raises(ValueError, match="download failed") as error:
        resolve_model_path(hf_settings(model_local_path=tmp_path))
    assert "PRIVATE_TOKEN" not in str(error.value)
    download.side_effect = None
    download.return_value = str(tmp_path)
    with pytest.raises(ValueError, match="does not contain"):
        resolve_model_path(hf_settings())


def test_dotenv_reads_model_source_with_environment_override(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("MODEL_SOURCE=hf\nHF_MODEL_ID=org/model\nHF_MODEL_REVISION=" + "a" * 40 + "\n")
    settings = Settings(_env_file=env_file, environment="test", ml_internal_api_key="test")
    assert settings.model_source == "hf" and settings.hf_model_id == "org/model"
    monkeypatch.setenv("MODEL_SOURCE", "local")
    assert (
        Settings(_env_file=env_file, environment="test", ml_internal_api_key="test").model_source == "local"
    )


def test_hub_cache_symlinks_become_self_contained_and_external_links_are_rejected(tmp_path):
    cache = tmp_path / "cache"
    model = cache / "snapshots/revision/model"
    model.mkdir(parents=True)
    blob = cache / "blobs/weights"
    blob.parent.mkdir()
    blob.write_bytes(b"controlled-model-data")
    try:
        (model / "model.safetensors").symlink_to(blob)
    except OSError:
        pytest.skip("OS does not permit creating symlinks")
    settings = hf_settings(hf_cache_dir=cache)
    result = materialize_cache_links(model, settings)
    assert (result / "model.safetensors").read_bytes() == blob.read_bytes()
    assert not (result / "model.safetensors").is_symlink()
    assert materialize_cache_links(model, settings) == result
    outside = tmp_path / "outside"
    outside.write_bytes(b"must-not-copy")
    (model / "outside.json").symlink_to(outside)
    with pytest.raises(ValueError, match="Unsafe links"):
        materialize_cache_links(model, settings)
