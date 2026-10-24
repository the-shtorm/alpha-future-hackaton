"""Verify the Git LFS inference package offline; optionally run a real CPU smoke test."""

import argparse
import json
from pathlib import Path

from app.core.config import ROOT, Settings, locked_model
from app.services.encoder import SentenceEncoder, verify_finetuned_manifest


def check_lfs_download(directory: Path):
    weights = directory / "model.safetensors"
    if not weights.is_file():
        raise ValueError("Model weights are missing; run git lfs install and git lfs pull")
    with weights.open("rb") as source:
        if source.read(128).startswith(b"version https://git-lfs.github.com/spec/v1"):
            raise ValueError("Weights are still a Git LFS pointer; run git lfs pull before starting ML")


def verify_package(directory: Path, smoke: bool = False) -> dict:
    check_lfs_download(directory)
    lock = locked_model("finetuned")
    manifest = verify_finetuned_manifest(directory, lock["revision"])
    if (
        manifest["localModelId"] != lock["modelId"]
        or manifest["baseModelId"] != lock["baseModelId"]
        or manifest["baseRevision"] != lock["baseRevision"]
        or manifest["dimension"] != 384
        or manifest["maxSeqLength"] != 512
    ):
        raise ValueError("Model metadata differs from the runtime lock")
    settings = Settings(
        model_variant="finetuned",
        model_local_path=directory,
        environment="test",
        ml_internal_api_key="local-model-package-check",
    )
    result = {
        "verified": True,
        "modelId": manifest["localModelId"],
        "artifactSha256": manifest["artifactSha256"],
        "checkedFiles": len(manifest["checksums"]),
        "dimension": 384,
        "maxSeqLength": 512,
        "maxCosineDistance": settings.recommendation_max_cosine_distance,
        "smoke": "not_requested",
    }
    if smoke:
        encoder = SentenceEncoder(settings)
        texts = ["query: Нужны средства на оборудование.", "passage: Покупка станка для производства."]
        if max(encoder.token_lengths(texts)) > 512:
            raise ValueError("Smoke texts exceed the model token limit")
        vectors = encoder.encode(texts)  # Runtime validates shape, finite values and unit norms.
        result["smoke"] = {"device": "cpu", "dtype": str(vectors.dtype), "shape": list(vectors.shape)}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", type=Path, default=ROOT / "models/e5-credit-finetune-v1/final")
    parser.add_argument(
        "--smoke", action="store_true", help="Load local weights and encode Russian texts on CPU"
    )
    args = parser.parse_args()
    try:
        result = verify_package(args.model_path, args.smoke)
    except (ValueError, KeyError, OSError) as error:
        parser.exit(
            1,
            f"Model package verification failed ({type(error).__name__}). Run git lfs pull and check the model manifest.\n",
        )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
