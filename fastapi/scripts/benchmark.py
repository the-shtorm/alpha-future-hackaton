"""Real-model HTTP benchmark through the ASGI client; no synthetic timing claims."""
# ruff: noqa: E402

import time

PROCESS_START = time.perf_counter()

import argparse
import copy
import importlib.metadata
import json
import platform
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import psutil
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def cgroup_memory():
    values = {}
    for name in ("memory.current", "memory.peak", "memory.max"):
        path = Path("/sys/fs/cgroup") / name
        if path.is_file():
            values[name] = path.read_text().strip()
    return values or None


def benchmark(settings, iterations):
    process = psutil.Process()
    peak = [process.memory_info().rss]
    stop = threading.Event()

    def monitor():
        while not stop.wait(0.01):
            peak[0] = max(peak[0], process.memory_info().rss)

    sampler = threading.Thread(target=monitor, daemon=True)
    sampler.start()
    app = create_app(settings)
    rows = []
    try:
        with TestClient(app) as client:
            cold_start = time.perf_counter() - PROCESS_START
            base = json.loads(Path("examples/rank-request.json").read_text(encoding="utf-8"))
            headers = {"X-Internal-API-Key": settings.ml_internal_api_key}
            for count in (1, 10, 100):
                body = copy.deepcopy(base)
                body["candidates"] = []
                for i in range(count):
                    item = copy.deepcopy(base["candidates"][i % len(base["candidates"])])
                    item["product"]["id"] = f"bench-{i:03}"
                    item["product"]["targetScenario"] += f" Демонстрационный вариант {i}."
                    body["candidates"].append(item)

                def call(_, body=body):
                    start = time.perf_counter()
                    result = client.post("/api/v1/recommendations/rank", json=body, headers=headers)
                    if result.status_code != 200:
                        raise RuntimeError(f"Benchmark HTTP {result.status_code}: {result.text}")
                    return (time.perf_counter() - start) * 1000

                app.state.runner.ranker.cache.values.clear()
                cold = call(0)
                for concurrency in (1, 4):
                    with ThreadPoolExecutor(max_workers=concurrency) as pool:
                        durations = list(pool.map(call, range(iterations)))
                    rows.append(
                        {
                            "candidateCount": count,
                            "concurrency": concurrency,
                            "iterations": iterations,
                            "coldRequestMs": cold,
                            "warmP50Ms": float(np.percentile(durations, 50)),
                            "warmP95Ms": float(np.percentile(durations, 95)),
                        }
                    )
            info = client.get("/api/v1/model-info", headers=headers).json()
    finally:
        stop.set()
        sampler.join()
    return {
        "transport": "in-process HTTP/ASGI; includes API validation, queue and serialization",
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": platform.processor(),
        "logicalCpuCount": psutil.cpu_count(),
        "hostRamBytes": psutil.virtual_memory().total,
        "coldStartSeconds": cold_start,
        "sampledPeakRssBytes": peak[0],
        "osMemoryInfo": process.memory_info()._asdict(),
        "cgroupMemory": cgroup_memory(),
        "model": info,
        "versions": {n: importlib.metadata.version(n) for n in ("torch", "sentence-transformers", "fastapi")},
        "measurements": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--output", type=Path, default=Path("reports/benchmark.json"))
    args = parser.parse_args()
    if args.iterations < 4:
        parser.error("--iterations must be at least 4")
    report = benchmark(Settings(), args.iterations)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
