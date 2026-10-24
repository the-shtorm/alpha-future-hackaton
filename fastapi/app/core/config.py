from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
MODEL_ID = "intfloat/multilingual-e5-small"
VERSIONS = dict(
    queryTemplateVersion="query-v2",
    passageTemplateVersion="passage-v2",
    labelsVersion="ru-v2",
    contractVersion="rank-v2",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    environment: str = "production"
    ml_internal_api_key: str = ""
    model_id: str = MODEL_ID
    model_revision: str = ""
    model_local_path: Path = ROOT / "models" / "multilingual-e5-small"
    embedding_batch_size: int = Field(default=4, ge=1, le=32)
    torch_num_threads: int = Field(default=2, ge=1)
    torch_num_interop_threads: int = Field(default=1, ge=1)
    passage_cache_max_entries: int = Field(default=512, ge=1, le=10000)
    max_inflight_rank_requests: int = Field(default=4, ge=1, le=4)
    admission_timeout_seconds: float = Field(default=1, gt=0, le=1)
    max_request_bytes: int = Field(default=524288, ge=1, le=524288)
    docs_enabled: bool = False
    log_level: str = "INFO"

    @model_validator(mode="after")
    def validate_runtime(self):
        key = self.ml_internal_api_key.strip()
        if not key or (
            self.environment != "test"
            and (len(key) < 32 or any(s in key.lower() for s in ("replace", "example", "change-me")))
        ):
            raise ValueError("ML_INTERNAL_API_KEY must be a non-example secret of at least 32 characters")
        if self.model_id != MODEL_ID:
            raise ValueError("Only the contracted model is supported")
        self.ml_internal_api_key = key
        return self
