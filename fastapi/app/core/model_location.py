"""A single MODEL_PATH selects local disk, Hugging Face, or an S3-compatible prefix."""

import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname


def parse_model_path(value: str, root: Path) -> dict:
    value = value.strip()
    if not value:
        raise ValueError("MODEL_PATH must not be empty")
    if value.startswith("https://huggingface.co/"):
        value = "hf://" + value.removeprefix("https://huggingface.co/")
    if value.startswith("hf://"):
        raw = value.removeprefix("hf://")
    elif (
        re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value)
        and not (root / value).exists()
        and not value.startswith("models/")
        and not value.startswith(".")
    ):
        raw = value
    else:
        raw = None
    if raw is not None:
        if "?" in raw or "#" in raw:
            raise ValueError("HF MODEL_PATH must not contain query parameters or fragments")
        parts = raw.split("/", 2)
        if len(parts) < 2:
            raise ValueError("HF MODEL_PATH must include namespace/repository")
        owner, repository = parts[:2]
        repository, separator, revision = repository.partition("@")
        repo_id = owner + "/" + repository
        folder = parts[2] if len(parts) == 3 else "model"
        if not separator:
            lock = json.loads((root / "config/hf-deployment.lock.json").read_text(encoding="utf-8"))
            if lock["repoId"] != repo_id:
                raise ValueError("Unknown HF repository requires @<immutable commit SHA> in MODEL_PATH")
            revision = lock["revision"]
        return {
            "model_source": "hf",
            "hf_model_id": repo_id,
            "hf_model_revision": revision,
            "hf_model_subfolder": folder,
        }
    if value.startswith("s3://"):
        uri = urlsplit(value)
        if not uri.netloc or "@" in uri.netloc or ":" in uri.netloc or uri.query or uri.fragment:
            raise ValueError("S3 MODEL_PATH must be s3://bucket/prefix, without credentials or query")
        return {"model_source": "s3", "s3_bucket": uri.netloc, "s3_prefix": unquote(uri.path).strip("/")}
    if value.startswith("file://"):
        uri = urlsplit(value)
        if uri.netloc not in ("", "localhost"):
            raise ValueError("file:// MODEL_PATH must refer to local disk")
        value = url2pathname(unquote(uri.path))
    elif "://" in value:
        raise ValueError("MODEL_PATH supports local paths, hf:// and s3://")
    local = Path(value).expanduser()
    return {"model_source": "local", "model_local_path": local if local.is_absolute() else root / local}
