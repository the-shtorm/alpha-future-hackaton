"""Download only the pinned public safetensors/tokenizer assets for the local experiment."""

import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
from pathlib import Path

from app.core.config import ROOT


def main():
    lock = json.loads((ROOT / "config/reranker-experiment.lock.json").read_text(encoding="utf-8"))
    directory = ROOT / "models/mmarco-minilm-reranker"
    env = dict(
        os.environ, HF_HUB_OFFLINE="0", HF_HUB_DISABLE_TELEMETRY="1", HF_HUB_DISABLE_IMPLICIT_TOKEN="1"
    )
    cli = Path(sys.executable).with_name("hf.exe" if os.name == "nt" else "hf")
    assets = [
        "config.json",
        "model.safetensors",
        "tokenizer.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "sentencepiece.bpe.model",
        "README.md",
    ]
    subprocess.run(
        [
            str(cli),
            "download",
            lock["modelId"],
            *assets,
            "--revision",
            lock["revision"],
            "--local-dir",
            str(directory),
        ],
        env=env,
        check=True,
    )
    checksums = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in assets}
    manifest = {
        **lock,
        "checksums": checksums,
        "versions": {
            name: importlib.metadata.version(name)
            for name in ("torch", "transformers", "sentence-transformers", "huggingface-hub")
        },
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"modelId": lock["modelId"], "revision": lock["revision"], "files": len(checksums)}))


if __name__ == "__main__":
    main()
