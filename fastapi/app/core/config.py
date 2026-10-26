import json
import math
import re
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.model_location import parse_model_path

ROOT = Path(__file__).resolve().parents[2]
MODEL_ID = "intfloat/multilingual-e5-small"
VERSIONS = dict(
    queryTemplateVersion="query-v2",
    passageTemplateVersion="passage-v2",
    labelsVersion="ru-v2",
    contractVersion="rank-v2",
)


def locked_model(variant: str) -> dict:
    name = "finetuned-model.lock.json" if variant == "finetuned" else "model.lock.json"
    return json.loads((ROOT / "config" / name).read_text(encoding="utf-8"))


def calibrated_distance(variant: str = "base") -> float | None:
    name = "finetuned-selection-policy.json" if variant == "finetuned" else "selection-policy.json"
    policy_file = ROOT / "config" / name
    if not policy_file.exists():
        return None
    policy = json.loads(policy_file.read_text(encoding="utf-8"))
    lock = locked_model(variant)
    if (
        policy["policyVersion"] != "top_k_cosine_distance_v1"
        or policy["modelId"] != lock.get("modelId", MODEL_ID)
        or policy["modelRevision"] != lock["revision"]
        or policy["templates"] != VERSIONS
    ):
        raise ValueError("Selection calibration does not match the locked model and templates")
    distance = policy["maxCosineDistance"]
    if type(distance) not in (int, float) or not math.isfinite(distance) or not 0 <= distance <= 2:
        raise ValueError("Invalid calibrated cosine distance")
    return distance


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore", env_ignore_empty=True, env_file=ROOT / ".env", env_file_encoding="utf-8"
    )
    environment: str = "production"
    ml_internal_api_key: str = ""
    model_variant: Literal["base", "finetuned"] = "finetuned"
    model_path: str | None = None
    model_source: Literal["local", "hf", "s3"] = "local"
    model_id: str = MODEL_ID
    model_revision: str = ""
    model_local_path: Path = ROOT / "models" / "multilingual-e5-small"
    hf_model_id: str | None = None
    hf_model_revision: str | None = None
    hf_model_subfolder: str = "model"
    hf_cache_dir: Path = ROOT / "models/hf-cache"
    hf_local_files_only: bool = False
    hf_token: SecretStr | None = Field(default=None, repr=False, exclude=True)
    s3_bucket: str | None = None
    s3_prefix: str = ""
    s3_endpoint_url: str | None = None
    aws_default_region: str | None = None
    aws_access_key_id: SecretStr | None = Field(default=None, repr=False, exclude=True)
    aws_secret_access_key: SecretStr | None = Field(default=None, repr=False, exclude=True)
    aws_session_token: SecretStr | None = Field(default=None, repr=False, exclude=True)
    embedding_batch_size: int = Field(default=4, ge=1, le=32)
    torch_num_threads: int = Field(default=2, ge=1)
    torch_num_interop_threads: int = Field(default=1, ge=1)
    passage_cache_max_entries: int = Field(default=512, ge=1, le=10000)
    recommendation_max_cosine_distance: float | None = Field(
        default=None,
        ge=0,
        le=2,
        allow_inf_nan=False,
        description="Maximum 1 - cosine similarity; defaults to the pinned synthetic calibration artifact.",
    )
    max_inflight_rank_requests: int = Field(default=4, ge=1, le=4)
    admission_timeout_seconds: float = Field(default=1, gt=0, le=1)
    max_request_bytes: int = Field(default=524288, ge=1, le=524288)
    docs_enabled: bool = False
    log_level: str = "INFO"
    scoring_enabled: bool = False
    scoring_model_path: str | Path = "thedauns/sba-scoring-v2"

    @model_validator(mode="after")
    def validate_runtime(self):
        if self.model_path is not None:
            for name, value in parse_model_path(self.model_path, ROOT).items():
                setattr(self, name, value)
        key = self.ml_internal_api_key.strip()
        if not key or (
            self.environment != "test"
            and (len(key) < 32 or any(s in key.lower() for s in ("replace", "example", "change-me")))
        ):
            raise ValueError("ML_INTERNAL_API_KEY must be a non-example secret of at least 32 characters")
        lock = locked_model(self.model_variant)
        expected_id = lock["modelId"]
        if "model_id" not in self.model_fields_set:
            self.model_id = expected_id
        if self.model_id != expected_id or (self.model_revision and self.model_revision != lock["revision"]):
            raise ValueError("Configured model identity differs from the selected model lock")
        self.model_revision = lock["revision"]
        if self.model_variant == "finetuned" and "model_local_path" not in self.model_fields_set:
            self.model_local_path = ROOT / "models/e5-credit-finetune-v1/final"
        if not self.model_local_path.is_absolute():
            self.model_local_path = ROOT / self.model_local_path
        if self.model_source == "hf":
            if not self.hf_model_id or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.hf_model_id):
                raise ValueError("HF_MODEL_ID must be namespace/repository")
            if not self.hf_model_revision or not re.fullmatch(r"[0-9a-f]{40}", self.hf_model_revision):
                raise ValueError("HF_MODEL_REVISION must be a pinned 40-character commit SHA")
            folder = self.hf_model_subfolder
            if "\\" in folder or folder.startswith("/") or any(p in (".", "..") for p in folder.split("/")):
                raise ValueError("HF_MODEL_SUBFOLDER must be a safe relative Hub path")
        if self.model_source == "s3" and not self.s3_bucket:
            raise ValueError("S3 source requires MODEL_PATH=s3://bucket/prefix")
        if "recommendation_max_cosine_distance" not in self.model_fields_set:
            self.recommendation_max_cosine_distance = calibrated_distance(self.model_variant)
        self.ml_internal_api_key = key
        return self
