"""Execute the versioned 90/60 research campaign with durable per-stage journals."""

import argparse
import concurrent.futures
import copy
import itertools
import json
import multiprocessing
from pathlib import Path

import numpy as np

from scoring_training.campaign_data import BUNDLES
from scoring_training.campaign_fit import initialize_worker, result_rank, run_trial, signature
from scoring_training.data import sha256_file
from scoring_training.train import read_json, write_json


def screening():
    configurations = []
    axes = ([None, 10, 7, 5, 3], [None, 1, 3, 5], [1, 1.5, 2, 3, 5, 8, "SqrtBalanced", "Balanced"], BUNDLES)
    for i, (window, half_life, balance, bundle) in enumerate(itertools.product(*axes)):
        configurations.append({"id": f"screen-v1-{i:04d}", "stage": "screening", "family": "catboost",
                               "bundle": bundle, "fold": "B", "window": window, "halfLife": half_life,
                               "balance": balance, "seed": 42, "parameters": {}})
    return configurations


def unique_successes(results):
    unique = {}
    for row in results:
        if row.get("status") == "complete" and not row.get("reusedFrom"):
            unique.setdefault(row["signature"], row)
    return list(unique.values())


def promote(results, per_bundle=4):
    good = unique_successes(results)
    return [row for bundle in BUNDLES
            for row in sorted((r for r in good if r["config"]["bundle"] == bundle),
                              key=result_rank, reverse=True)[:per_bundle]]


def refinement(parents):
    rng = np.random.default_rng(20261025)

    def choose(values):
        return values[int(rng.integers(len(values)))]

    configurations = []
    for parent in parents:
        for _ in range(30):
            grow = choose(["SymmetricTree", "Depthwise", "Lossguide"])
            boosting = choose(["Plain", "Ordered"]) if grow == "SymmetricTree" else "Plain"
            bootstrap = choose(["Bayesian", "Bernoulli"] if boosting == "Ordered"
                               else ["Bayesian", "Bernoulli", "MVS"])
            parameters = {
                "depth": choose([4, 5, 6, 7, 8, 10]), "learning_rate": choose([0.015, 0.03, 0.06, 0.1]),
                "l2_leaf_reg": choose([1, 3, 10, 30, 100]), "random_strength": choose([0, 0.5, 1, 2, 5]),
                "rsm": choose([0.6, 0.8, 1.0]), "border_count": choose([64, 128, 254]),
                "boosting_type": boosting, "bootstrap_type": bootstrap, "grow_policy": grow,
                "has_time": choose([False, True]),
            }
            if bootstrap == "Bayesian":
                parameters["bagging_temperature"] = choose([0, 0.5, 1, 3])
            else:
                parameters["subsample"] = choose([0.6, 0.8, 1.0])
            if grow != "SymmetricTree":
                parameters["min_data_in_leaf"] = choose([20, 100, 500])
            if grow == "Lossguide":
                parameters["max_leaves"] = choose([16, 32, 64])
            configurations.append({**parent["config"], "id": f"refine-{len(configurations):04d}",
                                   "stage": "refinement", "parent": parent["id"], "parameters": parameters})
    return configurations


def competitors(results):
    good = unique_successes(results)
    best = {bundle: max((r for r in good if r["config"]["bundle"] == bundle), key=result_rank)
            for bundle in BUNDLES[1:]}
    configurations = []

    def add(parent, family, parameters, balance=1):
        configurations.append({**parent["config"], "id": f"competitor-{len(configurations):04d}",
                               "stage": "competitors", "parent": parent["id"], "family": family,
                               "parameters": parameters, "balance": balance})

    for bundle, c, weight in itertools.product(BUNDLES[1:], [0.01, 0.1, 1, 10], [1, 3, 8]):
        add(best[bundle], "logistic", {"C": c}, weight)
    parent = max(best.values(), key=result_rank)
    for depth, leaf, features, weight in itertools.product([6, 12, None], [10, 50], [0.7, 1.0],
                                                          [None, "balanced_subsample"]):
        add(parent, "randomForest", {"max_depth": depth, "min_samples_leaf": leaf,
                                     "max_features": features, "class_weight": weight})
    rng = np.random.default_rng(20261026)

    def choose(values):
        return values[int(rng.integers(len(values)))]

    for family in ("lightgbm", "xgboost"):
        for i in range(60):
            parent = best[BUNDLES[1 + i % 2]]
            common = {"learning_rate": choose([0.02, 0.04, 0.08]), "subsample": choose([0.7, 0.9, 1.0]),
                      "colsample_bytree": choose([0.7, 0.9, 1.0]), "reg_lambda": choose([1, 10, 50]),
                      "reg_alpha": choose([0, 0.1, 1])}
            if family == "lightgbm":
                parameters = {**common, "num_leaves": choose([15, 31, 63]),
                              "min_child_samples": choose([50, 200, 500]), "subsample_freq": 1,
                              "metric": "average_precision"}
            else:
                parameters = {**common, "max_depth": choose([3, 5, 7]), "min_child_weight": choose([1, 5, 20]),
                              "max_delta_step": choose([0, 1, 5])}
            add(parent, family, parameters, choose([1, 2, 3, 5, 8]))
    return configurations


def warm_starts(results):
    good = [r for r in unique_successes(results) if r["config"]["bundle"] == BUNDLES[0]
            and r["config"].get("window") in (None, 10) and r["config"]["family"] == "catboost"]
    parent = max(good, key=result_rank)
    configurations = []
    for recent, replay, rate, count in itertools.product([3, 5], [0.25, 0.5], [0.01, 0.03, 0.06], [100, 300]):
        configurations.append({**parent["config"], "id": f"warm-{len(configurations):04d}", "stage": "warm",
                               "window": None, "parent": parent["id"], "initArtifact": parent["artifact"],
                               "replayFraction": replay, "recentWindow": recent,
                               "parameters": {**parent["config"]["parameters"], "learning_rate": rate,
                                              "iterations": count}})
    return configurations


def robust_configs(parents):
    configurations = []
    for parent, seed, fold in itertools.product(parents, [42, 137, 2026], ["A", "B", "C"]):
        configurations.append({**parent["config"], "id": f"robust-{len(configurations):04d}", "stage": "robustness",
                               "parent": parent["id"], "seed": seed, "fold": fold})
    return configurations


def protect_favorite(export, root):
    from app.scoring.package import ScoringPackage

    favorite = read_json(export / "favorite.json")
    for path in (Path("models/sba-scoring-v1"), root / "favorite-package"):
        ScoringPackage(path, favorite["manifestSha256"])
    lock = read_json(Path("config/scoring-model.lock.json"))
    if lock["manifestSha256"] != favorite["manifestSha256"]:
        raise ValueError("Favorite runtime pin changed")


def execute_batch(configurations, stage, root, workers):
    stage_dir = root / "stages"
    stage_dir.mkdir(exist_ok=True)
    write_json(stage_dir / f"{stage}-configs.json", configurations)
    cached = {}
    for file in (root / "trials").glob("*/result.json"):
        row = read_json(file)
        expected_source = row.get("implementationSha256", {})
        if row.get("status") == "complete" and all(
            expected_source.get(name) == sha256_file(Path(__file__).with_name(name))
            for name in ("campaign_fit.py", "campaign_data.py", "business_thresholds.py", "thresholds.py")
        ):
            cached.setdefault(row["signature"], row)
    groups, results = {}, []
    for config in configurations:
        groups.setdefault(signature(config), []).append(config)

    def received(row, configs):
        for config in configs:
            result = copy.deepcopy(row)
            if row["id"] != config["id"]:
                result.update(id=config["id"], config=config, reusedFrom=row["id"])
                directory = root / "trials" / config["id"]
                directory.mkdir(parents=True, exist_ok=True)
                write_json(directory / "result.json", result)
            results.append(result)
        good = [r for r in results if r.get("status") == "complete"]
        best = max(good, key=result_rank) if good else None
        progress = {"stage": stage, "completedRecords": len(results), "totalRecords": len(configurations),
                    "failedRecords": sum(r.get("status") != "complete" for r in results)}
        if best:
            metrics = best["validation"][best["primaryPolicy"]]
            progress["best"] = {"id": best["id"], "precision": metrics["precision"], "f1": metrics["f1"],
                                "recall": metrics["recall"], "threshold": metrics["threshold"],
                                "validationTargetPassed": best["validationTargetPassed"]}
        write_json(root / "progress.json", progress)
        with (root / "journal.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(progress) + "\n")
        print(json.dumps(progress), flush=True)

    pending = []
    for digest, configs in groups.items():
        if digest in cached:
            received(cached[digest], configs)
        else:
            pending.append(configs)
    if pending:
        with concurrent.futures.ProcessPoolExecutor(
            max_workers=workers, mp_context=multiprocessing.get_context("spawn"),
            initializer=initialize_worker, initargs=(root / "dataset.joblib", root),
        ) as pool:
            futures = {pool.submit(run_trial, configs[0]): configs for configs in pending}
            for future in concurrent.futures.as_completed(futures):
                received(future.result(), futures[future])
    results.sort(key=lambda r: r["id"])
    write_json(stage_dir / f"{stage}-results.json", results)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("scoring_training/runs/recall90-precision60-campaign-v1"))
    parser.add_argument("--export", type=Path, default=Path("experiments/sba-scoring-campaign-v1"))
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--stage", choices=["all", "screening", "refinement", "competitors", "warm", "robustness",
                                          "postprocess"], default="all")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    root = args.root.resolve()
    protect_favorite(args.export, root)
    protocol = read_json(root / "protocol.json")
    if sha256_file(root / "dataset.joblib") != protocol["cacheSha256"]:
        raise ValueError("Campaign cache changed")

    def stage(name, configs):
        path = root / "stages" / f"{name}-results.json"
        if args.stage in ("all", name):
            return execute_batch(configs[:args.limit] if args.limit else configs, name, root, args.workers)
        return read_json(path) if path.exists() else []

    screen = stage("screening", screening())
    refined = stage("refinement", refinement(promote(screen))) if screen else []
    developed = screen + refined
    other = stage("competitors", competitors(developed)) if developed else []
    warm = stage("warm", warm_starts(developed)) if developed else []
    candidates = developed + other
    parents = sorted(unique_successes(candidates), key=result_rank, reverse=True)[:10]
    robust = stage("robustness", robust_configs(parents)) if parents else []
    if args.stage in ("all", "postprocess"):
        from scoring_training.campaign_postprocess import postprocess

        postprocess(root, args.export, screen + refined + other + warm + robust, parents)
    protect_favorite(args.export, root)
    print(json.dumps({"completedStage": args.stage, "favoriteVerified": True}), flush=True)


if __name__ == "__main__":
    main()
