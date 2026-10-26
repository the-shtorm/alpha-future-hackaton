import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.core.config import ROOT, Settings
from app.scoring.source import PACKAGE_FILES, parse_scoring_location, resolve_scoring_path

SHA = "5a0049417dae97bdc8a341c89c705d7505563645"


def settings(tmp_path, **options):
    return Settings(
        _env_file=None,
        environment="test",
        ml_internal_api_key="test",
        hf_cache_dir=tmp_path / "cache",
        **options,
    )


@pytest.mark.parametrize(
    "value",
    [
        "thedauns/sba-scoring-v2",
        "hf://thedauns/sba-scoring-v2",
        "https://huggingface.co/thedauns/sba-scoring-v2",
        f"hf://thedauns/sba-scoring-v2@{SHA}/model",
        f"thedauns/sba-scoring-v2@{SHA}/model",
    ],
)
def test_hf_addresses_use_immutable_revision(value):
    assert parse_scoring_location(value) == {
        "repo_id": "thedauns/sba-scoring-v2",
        "revision": SHA,
        "folder": "model",
    }


def test_other_pinned_repository_and_subfolder():
    assert parse_scoring_location(f"hf://other/model@{SHA}/nested/model")["folder"] == "nested/model"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "hf://other/model",
        "hf://owner/model@main/model",
        "hf://owner/model@short/model",
        f"hf://owner/model@{SHA}/../model",
        f"hf://owner/model@{SHA}/model//sub",
        f"hf://owner/model@{SHA}/./model",
        f"hf://owner/model@{SHA}/model?token=secret",
        "https://other.test/model",
        "s3://bucket/model",
        "file://remote/model",
        "file:///tmp/model?secret",
    ],
)
def test_unsafe_or_unpinned_locations_are_rejected(value):
    with pytest.raises(ValueError):
        parse_scoring_location(value)


def test_local_paths_remain_local(tmp_path, monkeypatch):
    downloader = Mock(side_effect=AssertionError("Local paths must never download"))
    monkeypatch.setattr("huggingface_hub.snapshot_download", downloader)
    assert resolve_scoring_path(settings(tmp_path, scoring_model_path=tmp_path)) == tmp_path
    assert parse_scoring_location(tmp_path.as_uri())["path"] == tmp_path
    assert parse_scoring_location("./existing")["path"] == ROOT / "existing"
    assert parse_scoring_location("models/scoring")["path"] == ROOT / "models/scoring"
    (tmp_path / "owner/model").mkdir(parents=True)
    assert parse_scoring_location("owner/model", tmp_path)["path"] == tmp_path / "owner/model"
    downloader.assert_not_called()


def test_corrupt_transport_pin_is_rejected(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/scoring-hf.lock.json").write_text(
        json.dumps({"repoId": "thedauns/sba-scoring-v2", "revision": "main"})
    )
    with pytest.raises(ValueError, match="immutable"):
        parse_scoring_location("thedauns/sba-scoring-v2", tmp_path)


def snapshot(config):
    path = config.hf_cache_dir / "snapshots" / SHA
    model = path / "model"
    model.mkdir(parents=True)
    for name in PACKAGE_FILES:
        (model / name).write_text(name)
    return path


@pytest.mark.parametrize("token", [None, "private-fixture-secret"])
def test_download_is_pinned_allowlisted_and_cached(tmp_path, monkeypatch, token):
    config = settings(tmp_path, hf_token=token)
    source = snapshot(config)
    downloader = Mock(return_value=str(source))
    monkeypatch.setattr("huggingface_hub.snapshot_download", downloader)
    result = resolve_scoring_path(config)
    assert set(p.name for p in result.iterdir()) == set(PACKAGE_FILES)
    assert all(not p.is_symlink() and p.read_text() == p.name for p in result.iterdir())
    arguments = downloader.call_args.kwargs
    assert arguments["revision"] == SHA
    assert arguments["allow_patterns"] == ["model/" + name for name in PACKAGE_FILES]
    assert arguments["token"] == token
    assert "private-fixture-secret" not in repr(config) and "hf_token" not in config.model_dump()
    timestamps = {p.name: p.stat().st_mtime_ns for p in result.iterdir()}
    config.hf_local_files_only = True
    assert resolve_scoring_path(config) == result
    assert downloader.call_args.kwargs["local_files_only"] is True
    assert {p.name: p.stat().st_mtime_ns for p in result.iterdir()} == timestamps


@pytest.mark.parametrize("failure", ["download", "outside", "missing", "copy"])
def test_failed_download_never_publishes_partial_package_or_leaks(tmp_path, monkeypatch, failure):
    config = settings(tmp_path)
    source = snapshot(config)
    downloader = Mock(return_value=str(source))
    monkeypatch.setattr("huggingface_hub.snapshot_download", downloader)
    if failure == "download":
        downloader.side_effect = OSError("private-secret-path")
    elif failure == "outside":
        downloader.return_value = str(tmp_path / "outside")
    elif failure == "missing":
        (source / "model/model.cbm").unlink()
    else:
        monkeypatch.setattr("app.scoring.source.shutil.copyfile", Mock(side_effect=OSError("private-secret")))
    with pytest.raises(ValueError, match="HF scoring download failed") as error:
        resolve_scoring_path(config)
    assert "private-secret" not in str(error.value)
    assert not list(config.hf_cache_dir.glob("scoring-runtime-packages/*"))


def test_cache_race_reuses_complete_winner(tmp_path, monkeypatch):
    config = settings(tmp_path)
    source = snapshot(config)
    monkeypatch.setattr("huggingface_hub.snapshot_download", Mock(return_value=str(source)))

    def winner(path, destination):
        destination.mkdir()
        for file in path.iterdir():
            (destination / file.name).write_bytes(file.read_bytes())
        raise FileExistsError("Another startup published the same package")

    monkeypatch.setattr(Path, "rename", winner)
    assert len(list(resolve_scoring_path(config).iterdir())) == len(PACKAGE_FILES)


def test_rename_failure_without_winner_is_sanitized(tmp_path, monkeypatch):
    config = settings(tmp_path)
    source = snapshot(config)
    monkeypatch.setattr("huggingface_hub.snapshot_download", Mock(return_value=str(source)))
    monkeypatch.setattr(Path, "rename", Mock(side_effect=OSError("private-secret")))
    with pytest.raises(ValueError, match="HF scoring download failed"):
        resolve_scoring_path(config)


def test_snapshot_links_are_materialized_and_escaping_links_rejected(tmp_path, monkeypatch):
    config = settings(tmp_path)
    source = snapshot(config)
    blob = config.hf_cache_dir / "blob"
    blob.write_text("model.cbm")
    link = source / "model/model.cbm"
    link.unlink()
    try:
        link.symlink_to(blob)
    except OSError:
        pytest.skip("OS does not permit test symlinks")
    monkeypatch.setattr("huggingface_hub.snapshot_download", Mock(return_value=str(source)))
    assert not (resolve_scoring_path(config) / "model.cbm").is_symlink()
    link.unlink()
    outside = tmp_path / "outside-blob"
    outside.write_text("not trusted")
    link.symlink_to(outside)
    with pytest.raises(ValueError, match="HF scoring download failed"):
        resolve_scoring_path(config)


def test_dotenv_source_and_environment_precedence(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("SCORING_MODEL_PATH=thedauns/sba-scoring-v2\nHF_LOCAL_FILES_ONLY=true\n")
    config = Settings(_env_file=env, environment="test", ml_internal_api_key="test")
    assert config.scoring_model_path == "thedauns/sba-scoring-v2" and config.hf_local_files_only
    monkeypatch.setenv("SCORING_MODEL_PATH", str(tmp_path / "local"))
    assert Settings(_env_file=env, environment="test", ml_internal_api_key="test").scoring_model_path == str(
        tmp_path / "local"
    )
