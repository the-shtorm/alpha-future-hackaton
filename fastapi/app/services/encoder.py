import hashlib
import json
import os
import re
from pathlib import Path
from typing import Protocol

import numpy as np

from app.core.config import MODEL_ID, Settings, locked_model


class Encoder(Protocol):
    model_id: str
    revision: str
    dimension: int

    def token_lengths(self, texts: list[str]) -> list[int]: ...
    def encode(self, texts: list[str]) -> np.ndarray: ...


def validate_vectors(vectors, count):
    vectors = np.asarray(vectors, dtype=np.float32)
    if (
        vectors.shape != (count, 384)
        or not np.isfinite(vectors).all()
        or not np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-4)
    ):
        raise ValueError("Encoder returned invalid normalized vectors")
    return vectors


def verify_manifest(directory: Path, revision: str = "") -> dict:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    sha = manifest.get("revision", "")
    if manifest.get("modelId") != MODEL_ID or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Invalid model identity or revision in manifest")
    if revision and revision != sha:
        raise ValueError("Configured model revision differs from manifest")
    files = manifest.get("checksums", {})
    required = {"config.json", "modules.json", "1_Pooling/config.json", "tokenizer_config.json"}
    if not required.issubset(files) or not any(n.endswith(".safetensors") for n in files):
        raise ValueError("Incomplete model manifest")
    actual = {
        p.relative_to(directory).as_posix()
        for p in directory.rglob("*")
        if p.is_file() and p.name != "manifest.json" and ".cache" not in p.relative_to(directory).parts
    }
    if actual != set(files):
        raise ValueError("Model directory differs from manifest")
    for name, expected in files.items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory.resolve()) or path.suffix in (".bin", ".pkl", ".pickle", ".py"):
            raise ValueError("Unsafe model artifact")
        with path.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != expected:
                raise ValueError("Model checksum mismatch")
    return manifest


def verify_finetuned_manifest(directory: Path, revision: str = "") -> dict:
    manifest = json.loads((directory / "finetune-manifest.json").read_text(encoding="utf-8"))
    expected = manifest["checksums"]
    actual = {
        p.relative_to(directory).as_posix()
        for p in directory.rglob("*")
        if p.is_file() and p.name != "finetune-manifest.json"
    }
    if actual != set(expected):
        raise ValueError("Fine-tuned model file set differs from manifest")
    for name, checksum in expected.items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory.resolve()) or path.suffix in (".bin", ".pkl", ".py", ".pickle"):
            raise ValueError("Unsafe fine-tuned model artifact")
        with path.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != checksum:
                raise ValueError("Fine-tuned model checksum mismatch")
    artifact_hash = hashlib.sha256(json.dumps(expected, sort_keys=True).encode()).hexdigest()
    if artifact_hash != manifest["artifactSha256"] or (revision and artifact_hash != revision):
        raise ValueError("Fine-tuned model identity mismatch")
    return manifest


class SentenceEncoder:
    model_id = MODEL_ID
    dimension = 384

    def __init__(self, settings: Settings):
        if settings.model_variant == "finetuned":
            manifest = verify_finetuned_manifest(settings.model_local_path, settings.model_revision)
            lock = locked_model("finetuned")
            if (
                manifest["localModelId"] != settings.model_id
                or manifest["baseModelId"] != lock["baseModelId"]
                or manifest["baseRevision"] != lock["baseRevision"]
                or manifest["dimension"] != self.dimension
                or manifest["maxSeqLength"] != 512
            ):
                raise ValueError("Fine-tuned model metadata differs from runtime lock")
            self.revision = manifest["artifactSha256"]
        else:
            manifest = verify_manifest(settings.model_local_path, settings.model_revision)
            self.revision = manifest["revision"]
        self.model_id = settings.model_id
        os.environ["TOKENIZERS_PARALLELISM"] = "false"
        import torch
        from sentence_transformers import SentenceTransformer

        torch.set_num_threads(settings.torch_num_threads)
        if torch.get_num_interop_threads() != settings.torch_num_interop_threads:
            torch.set_num_interop_threads(settings.torch_num_interop_threads)
        self.model = SentenceTransformer(
            str(settings.model_local_path),
            device="cpu",
            local_files_only=True,
            trust_remote_code=False,
            model_kwargs={"torch_dtype": torch.float32},
        )
        self.model.max_seq_length = 512
        self.model.default_prompt_name = None
        self.batch_size = settings.embedding_batch_size
        if self.model.get_sentence_embedding_dimension() != self.dimension:
            raise ValueError("Unexpected model dimension")

    def token_lengths(self, texts):
        return [
            len(ids)
            for ids in self.model.tokenizer(texts, add_special_tokens=True, truncation=False, padding=False)[
                "input_ids"
            ]
        ]

    def encode(self, texts):
        return validate_vectors(
            self.model.encode(
                texts,
                batch_size=self.batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
                prompt="",
            ),
            len(texts),
        )
