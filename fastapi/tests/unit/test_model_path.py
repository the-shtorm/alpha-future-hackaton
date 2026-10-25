import json

import pytest

from app.core.config import Settings, locked_model
from app.core.model_location import parse_model_path


def test_single_variable_overrides_legacy_source_fields(tmp_path):
    local = Settings(
        model_path=str(tmp_path), model_source="hf", environment="test", ml_internal_api_key="test"
    )
    assert local.model_source == "local" and local.model_local_path == tmp_path
    hf = Settings(
        model_path="hf://org/model@" + "a" * 40 + "/model", environment="test", ml_internal_api_key="test"
    )
    assert hf.model_source == "hf" and hf.hf_model_id == "org/model" and hf.hf_model_revision == "a" * 40
    s3 = Settings(model_path="s3://bucket/prefix/model", environment="test", ml_internal_api_key="test")
    assert s3.model_source == "s3" and s3.s3_bucket == "bucket" and s3.s3_prefix == "prefix/model"
    assert s3.model_revision == locked_model("finetuned")["revision"]


def test_bare_known_hf_id_uses_pinned_deployment_revision(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/hf-deployment.lock.json").write_text(
        json.dumps({"repoId": "org/model", "revision": "a" * 40})
    )
    values = parse_model_path("org/model", tmp_path)
    assert values["model_source"] == "hf" and values["hf_model_revision"] == "a" * 40
    assert parse_model_path("https://huggingface.co/org/model", tmp_path) == values
    with pytest.raises(ValueError, match="requires @"):
        parse_model_path("hf://other/model", tmp_path)


def test_local_relative_and_file_uri(tmp_path):
    assert parse_model_path("./existing", tmp_path)["model_local_path"] == tmp_path / "existing"
    assert parse_model_path("models/absent", tmp_path)["model_source"] == "local"
    local = tmp_path / "directory with space"
    assert parse_model_path(local.as_uri(), tmp_path)["model_local_path"] == local


@pytest.mark.parametrize(
    "value",
    [
        "",
        "http://example.com/model",
        "s3:///prefix",
        "s3://user@bucket/key",
        "s3://bucket/key?token=bad",
        "file://other-host/path",
        "hf://org/model@" + "a" * 40 + "/model?token=bad",
    ],
)
def test_unsafe_or_ambiguous_remote_paths_are_rejected(tmp_path, value):
    with pytest.raises(ValueError):
        parse_model_path(value, tmp_path)


def test_dotenv_only_model_path_is_enough_to_choose_source(tmp_path):
    env = tmp_path / ".env"
    env.write_text("MODEL_PATH=s3://bucket/released-model\n")
    settings = Settings(_env_file=env, environment="test", ml_internal_api_key="test")
    assert settings.model_source == "s3" and settings.s3_prefix == "released-model"
