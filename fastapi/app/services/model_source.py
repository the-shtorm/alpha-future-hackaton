"""Resolve a local or pinned Hugging Face package before the encoder is initialized."""

import hashlib
import shutil
import tempfile
from pathlib import Path

from app.core.config import Settings


def materialize_cache_links(model: Path, settings: Settings) -> Path:
    links = [p for p in model.rglob("*") if p.is_symlink()]
    if not links:
        return model
    cache = settings.hf_cache_dir.resolve()
    if any(p.is_dir() or not p.resolve().is_relative_to(cache) for p in links):
        raise ValueError("Unsafe links in Hugging Face cache")
    # Hub snapshots normally link files into blobs/. The strict model verifier
    # intentionally accepts self-contained folders only, so retain a regular-file copy.
    key = hashlib.sha256(
        f"{settings.hf_model_id}@{settings.hf_model_revision}/{settings.hf_model_subfolder}".encode()
    ).hexdigest()
    parent = cache / "runtime-packages"
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / key
    if not target.resolve().is_relative_to(cache):
        raise ValueError("Unsafe runtime cache path")
    if not target.exists():
        with tempfile.TemporaryDirectory(prefix=".model-", dir=parent) as temporary:
            stage = Path(temporary) / "model"
            shutil.copytree(model, stage, symlinks=False)
            try:
                stage.rename(target)
            except OSError:
                if not target.is_dir():
                    raise
    return target


def resolve_model_path(settings: Settings) -> Path:
    if settings.model_source == "local":
        return settings.model_local_path
    if settings.model_source == "s3":
        from app.services.s3_source import resolve_s3_model

        return resolve_s3_model(settings)
    from huggingface_hub import snapshot_download

    folder = settings.hf_model_subfolder
    patterns = [f"{folder}/**"] if folder else None
    try:
        snapshot = Path(
            snapshot_download(
                repo_id=settings.hf_model_id,
                repo_type="model",
                revision=settings.hf_model_revision,
                cache_dir=settings.hf_cache_dir,
                token=settings.hf_token.get_secret_value() if settings.hf_token else None,
                allow_patterns=patterns,
                local_files_only=settings.hf_local_files_only,
                max_workers=4,
            )
        )
    except Exception:
        raise ValueError(
            "Hugging Face model download failed; check pinned revision, access and cache"
        ) from None
    model = snapshot / folder if folder else snapshot
    if not model.is_dir() or not model.resolve().is_relative_to(snapshot.resolve()):
        raise ValueError("Hugging Face snapshot does not contain the configured model folder")
    return materialize_cache_links(model, settings)
