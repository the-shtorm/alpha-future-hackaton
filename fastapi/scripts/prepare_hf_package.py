"""Prepare a reproducible HF upload folder without secrets, caches or training checkpoints."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from app.core.config import ROOT, locked_model
from app.services.encoder import verify_finetuned_manifest


def prepare(output: Path):
    model = ROOT / "models/e5-credit-finetune-v1/final"
    lock = locked_model("finetuned")
    manifest = verify_finetuned_manifest(model, lock["revision"])
    output = output.resolve()
    if output.exists():
        raise FileExistsError("Use a new output directory; existing upload packages are not overwritten")
    if output.is_relative_to(model.resolve()):
        raise ValueError("Output must be outside the frozen model folder")
    output.mkdir(parents=True)
    shutil.copytree(model, output / "model")
    service = output / "service"
    service.mkdir()
    for directory, pattern in (
        ("app", "*.py"),
        ("scripts", "*.py"),
        ("config", "*.json"),
        ("contracts", "*.json"),
        ("examples", "*.json"),
        ("evaluation", "*.json"),
    ):
        for path in sorted((ROOT / directory).rglob(pattern)):
            target = service / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    for name in (
        "pyproject.toml",
        "uv.lock",
        "requirements.txt",
        "requirements-test.txt",
        "Dockerfile",
        ".dockerignore",
        ".env.example",
        "MODEL_HANDOFF.md",
        "training/pyproject.toml",
        "training/uv.lock",
        "experiments/e5-credit-finetune-v1.json",
    ):
        target = service / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    card = f"""---
language: ru
license: mit
tags:
- sentence-transformers
- e5
- recommendation
- synthetic-data
---
# E5 credit semantic ranking

Fine-tuned `intfloat/multilingual-e5-small`, CPU float32, 384 dimensions, max 512 tokens.
Frozen inference assets are in `model/`; supporting service, vocabulary, API contracts,
training code, dependency locks and synthetic evaluation data are in `service/`.

Artifact SHA-256: `{manifest["artifactSha256"]}`.
Use `service/config/finetuned-selection-policy.json` for the active F1 threshold.
The HF commit SHA is a separate transport revision: pin it inside MODEL_PATH.

## FastAPI configuration
```
MODEL_PATH=hf://thedauns/e5-credit-finetune-v1@<immutable 40-character HF commit SHA>/model
HF_CACHE_DIR=/model-cache
```
For a private repository provide HF_TOKEN as an environment secret, never in source code.
The package is downloaded once at startup and verified against manifest and the service
lock before local CPU inference. Change only MODEL_PATH to use local disk or s3://bucket/prefix.
See service/MODEL_HANDOFF.md for full instructions.

Training: 1500 profiles, 10610 pairs, OnlineContrastiveLoss, 2 epochs, 1328 steps,
seed 20261024. Development 180, calibration 180, original test 90; common 15-product catalog.
Labels are SYNTHETIC_PROPOSED and need expert review. Previously inspected 90/15 examples
are diagnostic replay sets, not new independent tests or proof of real-customer quality.
This is semantic ranking, not financial eligibility or credit approval.

Keep every file inside model/ unchanged: exact bytes are covered by finetune-manifest.json.
Source model: https://huggingface.co/intfloat/multilingual-e5-small/tree/{manifest["baseRevision"]}
"""
    (output / "README.md").write_text(card, encoding="utf-8", newline="\n")
    checksums = {}
    for path in sorted(output.rglob("*")):
        if path.is_file():
            with path.open("rb") as source:
                checksums[path.relative_to(output).as_posix()] = hashlib.file_digest(
                    source, "sha256"
                ).hexdigest()
    (output / "package-manifest.json").write_text(
        json.dumps(
            {
                "modelArtifactSha256": manifest["artifactSha256"],
                "checksums": checksums,
                "notice": "Model and service snapshot only; no .env, tokens, caches, optimizer state or intermediate checkpoints.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return {"prepared": True, "artifactSha256": manifest["artifactSha256"], "files": len(checksums) + 1}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(prepare(parser.parse_args().output)))


if __name__ == "__main__":
    main()
