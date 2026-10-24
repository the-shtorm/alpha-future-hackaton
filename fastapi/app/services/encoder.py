import hashlib
import json
import os
import re
from pathlib import Path
from typing import Protocol

import numpy as np

from app.core.config import MODEL_ID, ROOT, Settings


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
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Model checksum mismatch")
    return manifest


class SentenceEncoder:
    model_id = MODEL_ID
    dimension = 384

    def __init__(self, settings: Settings):
        revision = settings.model_revision
        lock = ROOT / "config/model.lock.json"
        if not revision and lock.exists():
            revision = json.loads(lock.read_text(encoding="utf-8"))["revision"]
        manifest = verify_manifest(settings.model_local_path, revision)
        self.revision = manifest["revision"]
        os.environ["TOKENIZERS_PARALLELISM"] = "false"
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
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
