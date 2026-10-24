"""Explicit online preparation. The service itself never downloads model artifacts."""

import argparse
import hashlib
import importlib.metadata
import json
import re
import tempfile
from pathlib import Path

from app.core.config import MODEL_ID, Settings
from app.services.encoder import SentenceEncoder, verify_manifest


def smoke(directory, revision):
    encoder = SentenceEncoder(
        Settings(
            environment="test",
            ml_internal_api_key="preparation",
            model_local_path=directory,
            model_revision=revision,
        )
    )
    vectors = encoder.encode(
        ["query: Нужны средства на покупку оборудования.", "passage: Кредит для покупки оборудования."]
    )
    return {"dimension": int(vectors.shape[1]), "finiteAndNormalized": True}


def prepare(directory: Path, revision: str | None, resolve_main: bool, lock_file: Path):
    if lock_file.exists():
        locked = json.loads(lock_file.read_text(encoding="utf-8"))
        if locked["modelId"] != MODEL_ID or (revision and revision != locked["revision"]):
            raise ValueError("Model lock differs from requested model/revision")
        revision = locked["revision"]
    if (directory / "manifest.json").exists():
        manifest = verify_manifest(directory, revision or "")
        smoke(directory, manifest["revision"])
        return manifest
    from huggingface_hub import HfApi, snapshot_download

    if not revision:
        if not resolve_main:
            raise ValueError("Initial preparation requires --revision SHA or --resolve-main")
        revision = HfApi().model_info(MODEL_ID, revision="main").sha
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Revision must be a complete commit SHA")
    if directory.exists():
        raise ValueError("Destination exists without a manifest; use a new empty destination")
    directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".prepare-", dir=directory.parent) as temporary:
        stage = Path(temporary) / "snapshot"
        snapshot_download(
            MODEL_ID,
            revision=revision,
            local_dir=stage,
            allow_patterns=[
                "*.json",
                "*.safetensors",
                "*.txt",
                "*.model",
                "README.md",
                "LICENSE*",
                "1_Pooling/config.json",
            ],
            ignore_patterns=["onnx/*", "openvino/*", "*.bin", "*.py"],
        )
        files = {
            p.relative_to(stage).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(stage.rglob("*"))
            if p.is_file() and ".cache" not in p.relative_to(stage).parts
        }
        manifest = {
            "modelId": MODEL_ID,
            "revision": revision,
            "checksums": files,
            "versions": {
                n: importlib.metadata.version(n)
                for n in ("torch", "sentence-transformers", "transformers", "huggingface-hub")
            },
        }
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        manifest["preparationSmoke"] = smoke(stage, revision)
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        stage.rename(directory)
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file.write_text(
        json.dumps({"modelId": MODEL_ID, "revision": revision}, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("models/multilingual-e5-small"))
    parser.add_argument("--revision")
    parser.add_argument("--resolve-main", action="store_true")
    parser.add_argument("--lock-file", type=Path, default=Path("config/model.lock.json"))
    args = parser.parse_args()
    manifest = prepare(args.directory.resolve(), args.revision, args.resolve_main, args.lock_file)
    print(json.dumps({"modelId": MODEL_ID, "revision": manifest["revision"], "smoke": "passed"}))


if __name__ == "__main__":
    main()
