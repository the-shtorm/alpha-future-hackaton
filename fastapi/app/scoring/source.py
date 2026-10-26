"""Resolve a local directory or a pinned HF package before native scoring loading."""

import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname

from app.core.config import ROOT

PACKAGE_FILES = (
    "manifest.json",
    "model.cbm",
    "calibration.json",
    "domain.json",
    "training.json",
    "evaluation.json",
)
REPOSITORY = r"[A-Za-z0-9_][A-Za-z0-9_.-]*/[A-Za-z0-9_][A-Za-z0-9_.-]*"


def parse_scoring_location(value, root=ROOT):
    value = str(value).strip()
    if not value:
        raise ValueError("SCORING_MODEL_PATH must not be empty")
    value = (
        value.replace("https://huggingface.co/", "hf://", 1)
        if value.startswith("https://huggingface.co/")
        else value
    )
    bare = re.fullmatch(REPOSITORY + r"(?:@[0-9a-f]{40}(?:/.*)?)?", value)
    if bare and not value.startswith(("models/", ".")) and not (root / value).exists():
        value = "hf://" + value
    if value.startswith("hf://"):
        match = re.fullmatch(
            r"hf://(?P<repo>"
            + REPOSITORY
            + r")(?:@(?P<revision>[0-9a-f]{40}))?(?:/(?P<folder>[A-Za-z0-9_./-]+))?",
            value,
        )
        if not match:
            raise ValueError("HF scoring path requires namespace/repository and an immutable SHA")
        repo, revision = match["repo"], match["revision"]
        folder = match["folder"] or "model"
        if any(part in ("", ".", "..") for part in folder.split("/")):
            raise ValueError("HF scoring subfolder must be a safe relative path")
        if revision is None:
            lock = json.loads((root / "config/scoring-hf.lock.json").read_text(encoding="utf-8"))
            if repo != lock["repoId"]:
                raise ValueError("An unknown HF repository requires @<immutable commit SHA>")
            revision = lock["revision"]
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError("HF scoring revision must be an immutable SHA")
        return {"repo_id": repo, "revision": revision, "folder": folder}
    if value.startswith("file://"):
        uri = urlsplit(value)
        if uri.netloc not in ("", "localhost") or uri.query or uri.fragment:
            raise ValueError("Scoring file URI must refer to local disk")
        value = url2pathname(unquote(uri.path))
    elif "://" in value:
        raise ValueError("SCORING_MODEL_PATH supports local folders and hf:// paths")
    path = Path(value).expanduser()
    return {"path": path if path.is_absolute() else root / path}


def resolve_scoring_path(settings):
    location = parse_scoring_location(settings.scoring_model_path)
    if "path" in location:
        return location["path"]
    from huggingface_hub import snapshot_download

    cache = Path(settings.hf_cache_dir).expanduser()
    cache = (cache if cache.is_absolute() else ROOT / cache).resolve()
    folder = location["folder"]
    key = hashlib.sha256(f"{location['repo_id']}@{location['revision']}/{folder}".encode()).hexdigest()
    target = cache / "scoring-runtime-packages" / key
    try:
        snapshot = Path(
            snapshot_download(
                repo_id=location["repo_id"],
                repo_type="model",
                revision=location["revision"],
                cache_dir=cache,
                allow_patterns=[f"{folder}/{name}" for name in PACKAGE_FILES],
                token=settings.hf_token.get_secret_value() if settings.hf_token else None,
                local_files_only=settings.hf_local_files_only,
                max_workers=4,
            )
        )
        source = snapshot / folder
        if not target.resolve().is_relative_to(cache) or not source.resolve().is_relative_to(cache):
            raise ValueError("Unsafe scoring cache path")
        # Hub snapshots link files into blobs/. Native package validation requires
        # self-contained directories; materialize only the six allowlisted files.
        for name in PACKAGE_FILES:
            file = source / name
            if not file.is_file() or not file.resolve().is_relative_to(cache):
                raise ValueError("Incomplete or unsafe HF scoring snapshot")
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix=".scoring-", dir=target.parent) as temporary:
                stage = Path(temporary) / "model"
                stage.mkdir()
                for name in PACKAGE_FILES:
                    shutil.copyfile(source / name, stage / name)
                try:
                    stage.rename(target)
                except OSError:
                    if not target.is_dir():
                        raise
        return target
    except Exception:
        raise ValueError("HF scoring download failed; check pinned revision, access and cache") from None
