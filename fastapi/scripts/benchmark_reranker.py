"""Measure the two pinned models under an external container memory/CPU limit; no test-set tuning."""

import argparse
import json
import threading
import time
from pathlib import Path

import psutil

from app.core.config import Settings
from app.services.encoder import SentenceEncoder
from scripts.calibrate import load_data
from scripts.reranker_experiment import LocalReranker, benchmark


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    process = psutil.Process()
    peak = [process.memory_info().rss]
    stop = threading.Event()

    def sample():
        while not stop.wait(0.01):
            peak[0] = max(peak[0], process.memory_info().rss)

    monitor = threading.Thread(target=sample, daemon=True)
    monitor.start()
    try:
        start = time.perf_counter()
        catalog, calibration, _ = load_data()
        encoder = SentenceEncoder(Settings(model_variant="base", recommendation_max_cosine_distance=None))
        reranker = LocalReranker()
        load_seconds = time.perf_counter() - start
        result = benchmark(encoder, reranker, catalog, calibration["scenarios"][0])
        result.update(
            bothModelsLoadSeconds=load_seconds,
            sampledPeakRssBytes=peak[0],
            currentRssBytes=process.memory_info().rss,
        )
        result["cgroupMemory"] = {
            name: Path("/sys/fs/cgroup", name).read_text().strip()
            for name in ("memory.current", "memory.peak", "memory.max")
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result), flush=True)
    finally:
        stop.set()
        monitor.join()


if __name__ == "__main__":
    main()
