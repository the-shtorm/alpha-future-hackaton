"""Commit completed aggregate stages without touching unrelated staged/unstaged work."""

import argparse
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from scoring_training.campaign_fit import result_rank
from scoring_training.campaign_postprocess import export_tables
from scoring_training.data import sha256_file
from scoring_training.train import read_json, write_json

REPORT = "docs/agents/2026-10-25-scoring-experiment-campaign.md"
EXPORT = "fastapi/experiments/sba-scoring-campaign-v1"
INDEX = "docs/agents/log.md"
STAGES = ("screening", "refinement", "competitors", "warm", "robustness", "postprocess")


def git(repo, *args, env=None, input=None):
    return subprocess.check_output(["git", *args], cwd=repo, env=env, input=input)


def commit_selected(repo, paths, message, index_update=None):
    """A private index excludes unrelated staged changes; then sync only our entries."""
    paths = sorted(set(paths))
    for name in paths:
        allowed = name == REPORT or name.startswith(EXPORT + "/")
        if not allowed or Path(name).suffix not in (".md", ".json", ".csv", ".png"):
            raise ValueError("Commit path is outside aggregate campaign artifacts")
        if not (repo / name).resolve().is_relative_to(repo.resolve()):
            raise ValueError("Commit path escapes repository")
    changed_index_text = None
    if index_update:
        old, new = index_update
        if "2026-10-25-scoring-experiment-campaign.md" not in old or \
                "2026-10-25-scoring-experiment-campaign.md" not in new:
            raise ValueError("Index update is outside this campaign's entry")
        if INDEX in git(repo, "diff", "--cached", "--name-only").decode().splitlines():
            raise ValueError("Shared report index is staged externally; refusing to overwrite")
        base = git(repo, "show", f"HEAD:{INDEX}").decode()
        if base.count(old) == 1:
            changed_index_text = base.replace(old, new)
        elif base.count(new) == 1:
            changed_index_text = base
        else:
            raise ValueError("Campaign index entry mismatch")
    with tempfile.TemporaryDirectory(prefix="sba-stage-index-") as temporary:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(temporary) / "index")}
        git(repo, "read-tree", "HEAD", env=env)
        if paths:
            git(repo, "add", "--", *paths, env=env)
        if changed_index_text is not None:
            oid = git(repo, "hash-object", "-w", "--stdin", env=env,
                      input=changed_index_text.encode()).decode().strip()
            git(repo, "update-index", "--add", "--cacheinfo", f"100644,{oid},{INDEX}", env=env)
            paths.append(INDEX)
        changed = subprocess.run(["git", "diff", "--cached", "--quiet", "HEAD"], cwd=repo, env=env).returncode
        if changed not in (0, 1):
            raise ValueError("Cannot inspect private stage index")
        if changed:
            git(repo, "diff", "--cached", "--check", env=env)
            git(repo, "commit", "--quiet", "-m", message, env=env)
    if changed_index_text is not None:
        working = (repo / INDEX).read_text()
        old, new = index_update
        if working.count(old) != 1:
            raise ValueError("Working campaign index changed concurrently; commit retained")
        (repo / INDEX).write_text(working.replace(old, new))
    # Preserve every other real-index entry, including preexisting staged work.
    tree = git(repo, "ls-tree", "-rz", "HEAD", "--", *paths)
    for entry in tree.split(b"\0"):
        if not entry:
            continue
        metadata, name = entry.split(b"\t", 1)
        mode, _, oid = metadata.decode().split()
        git(repo, "update-index", "--add", "--cacheinfo", f"{mode},{oid},{name.decode()}")
    return git(repo, "rev-parse", "HEAD").decode().strip()


def snapshot_stage(repo, root, export, stage, rows):
    directory = export / "stages" / stage
    directory.mkdir(parents=True, exist_ok=True)
    export_tables(directory, rows)
    by_fold = {}
    for fold in ("A", "B", "C"):
        candidates = [r for r in rows if r.get("status") == "complete" and r["config"]["fold"] == fold]
        if not candidates:
            continue
        best_f1 = max(candidates, key=lambda r: r["validation"][r["primaryPolicy"]]["f1"])
        closest = max(candidates, key=result_rank)
        by_fold[fold] = {
            "maximumMeasuredF1": {"id": best_f1["id"], "point": best_f1["validation"][best_f1["primaryPolicy"]]},
            "closestToBothFloors": {"id": closest["id"], "point": closest["validation"][closest["primaryPolicy"]]},
        }
    summary = {"stage": stage, "records": len(rows),
               "failures": sum(r.get("status") != "complete" for r in rows),
               "distinctModelArtifacts": len({r["artifact"] for r in rows if r.get("status") == "complete"}),
               "byFold": by_fold, "metricsAreAveraged": False}
    write_json(directory / "summary.json", summary)
    report = repo / REPORT
    text = report.read_text()
    heading = f"### Completed stage: {stage}"
    if heading not in text:
        text += f"\n{heading}\n\n"
        text += (f"- {len(rows)} records; {summary['distinctModelArtifacts']} distinct saved artifacts; "
                 f"{summary['failures']} failed records. Exact per-point CSVs exported under `{directory.relative_to(repo)}`.\n")
        for fold, value in by_fold.items():
            row = value["maximumMeasuredF1"]
            point = row["point"]
            text += (f"- Fold {fold}, largest measured fixed-threshold validation F1: `{row['id']}`, "
                     f"threshold {point['threshold']:.17g}, precision **{point['precision']:.6f}**, "
                     f"F1 **{point['f1']:.6f}**, recall **{point['recall']:.6f}**.\n")
        report.write_text(text)
    return [REPORT, *[str(path.relative_to(repo)) for path in directory.iterdir() if path.is_file()]]


def finalize_report(repo, export):
    summary = read_json(export / "summary.json")
    retention = read_json(export / "retention.json")
    no_feasible = (summary["status"] == "complete_no_feasible" and summary["top10Count"] == 0
                   and retention.get("allTrialWeightsPreserved") is True
                   and retention["deletedFiles"] == 0 and retention["freedBytes"] == 0)
    if not retention["favoriteUntouched"] or not (retention["cleanupComplete"] or no_feasible):
        raise ValueError("Retention/favorite verification is incomplete")
    top = read_json(export / "top10.json")
    report = repo / REPORT
    text = report.read_text()
    heading = "## Final executed outcome"
    if heading not in text:
        text += f"\n{heading}\n\n"
        text += (f"- {summary['recordCount']} measured records, {summary['distinctBaseModelArtifacts']} "
                 f"distinct base-model artifacts, {len(summary['failedRecords'])} failed records.\n")
        if no_feasible:
            text += (f"- No candidate meets both active constraints {summary['activeTarget']}; "
                     "no fallback winner, no cleanup, all trial weights and favorite preserved.\n")
        else:
            text += (f"- Retained {summary['top10Count']} distinct top candidates and required inference dependencies; "
                     f"replay passed before deleting {retention['deletedFiles']} trial weight/prediction files "
                     f"({retention['freedBytes']} bytes). Favorite and all aggregate metrics/configs retained.\n")
        text += "- Final metrics refer to historical FY2023 validation; no fresh independent test or deployment is claimed.\n"
        for rank, candidate in enumerate(top["candidates"], 1):
            point = candidate["validation"][candidate["primaryPolicy"]]
            text += (f"- Rank {rank}, `{candidate['id']}`: threshold {point['threshold']:.17g}; "
                     f"precision **{point['precision']:.6f}**, F1 **{point['f1']:.6f}**, "
                     f"recall **{point['recall']:.6f}**.\n")
    text = text.replace("3. Execute screening, refinement, robustness, warm-start, competitors and ensembles — in progress.",
                        "3. Execute screening, refinement, robustness, warm-start, competitors and ensembles — complete.")
    text = text.replace("4. Compare actual operating points, export aggregate artifacts and finalize local commits — pending.",
                        "4. Compare actual operating points, export aggregate artifacts and finalize local commits — complete.")
    report.write_text(text)
    readme = export / "README.md"
    body = readme.read_text().replace("**Выполняется, итоговые метрики пока не объявлены.**",
                                    "**Программа завершена; фактические результаты в top10.csv/json и summary.json.**")
    if "## Итоговые топ-10" not in body:
        body += "\n## Итоговые топ-10\n\n[Таблица](top10.csv), [конфигурации и метрики](top10.json), [сохранённые веса и очистка](retention.json).\n"
        if no_feasible:
            body += "\nНи один вариант не выполнил оба текущих ограничения. Топ-10 пуст; все веса сохранены, очистки не было.\n"
        body += "\n| Место | Вариант | Порог | Precision | F1 | Recall |\n|---|---|---:|---:|---:|---:|\n"
        for rank, candidate in enumerate(top["candidates"], 1):
            row = candidate["validation"][candidate["primaryPolicy"]]
            body += (f"| {rank} | {candidate['id']} | {row['threshold']:.12g} | {row['precision']:.2%} | "
                     f"{row['f1']:.6f} | {row['recall']:.2%} |\n")
    readme.write_text(body)
    write_json(export / "artifact-hashes.json", {path.name: sha256_file(path) for path in export.iterdir()
                                                 if path.is_file() and path.name != "artifact-hashes.json"})
    line = next(line for line in (repo / INDEX).read_text().splitlines()
                if "2026-10-25-scoring-experiment-campaign.md" in line)
    outcome = ("full campaign, no jointly feasible candidate, all weights/favorite preserved" if no_feasible else
               "full campaign, verified top-10, favorite preserved, other weights pruned")
    new = line.split(") — ", 1)[0] + f") — completed; {outcome}; local commits only."
    paths = [REPORT, *[str(path.relative_to(repo)) for path in export.iterdir() if path.is_file()]]
    return paths, (line, new)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("scoring_training/runs/recall90-precision60-campaign-v1"))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    root = args.root.resolve()
    export = repo / EXPORT
    markers = root / "stage-commits"
    markers.mkdir(exist_ok=True)
    if git(repo, "branch", "--show-current").decode().strip() != "scoring_model":
        raise ValueError("Campaign commits require the authorized scoring_model branch")
    write_json(root / "committer-status.json", {"status": "running", "pid": os.getpid(),
                                               "nice": os.getpriority(os.PRIO_PROCESS, 0),
                                               "scope": "completed aggregate stages only; never push"})
    from scoring_training.campaign import protect_favorite

    try:
        while True:
            for stage in STAGES:
                source = root / "stages" / f"{stage}-results.json"
                marker = markers / f"{stage}.json"
                if not source.exists() or marker.exists():
                    continue
                if stage == "postprocess":
                    try:
                        progress = read_json(root / "progress.json")
                    except (json.JSONDecodeError, FileNotFoundError):
                        continue
                    if progress.get("stage") != "complete":
                        continue
                try:
                    rows = read_json(source)
                except json.JSONDecodeError:
                    continue
                if not rows:
                    continue
                if git(repo, "branch", "--show-current").decode().strip() != "scoring_model":
                    raise ValueError("Authorized campaign branch changed; refusing stage commit")
                protect_favorite(export, root)
                paths = snapshot_stage(repo, root, export, stage, rows)
                update = None
                if stage == "postprocess":
                    if not (export / "retention.json").exists():
                        continue
                    final_paths, update = finalize_report(repo, export)
                    paths.extend(final_paths)
                commit = commit_selected(repo, paths, f"docs(scoring): record completed campaign {stage}", update)
                write_json(marker, {"stage": stage, "commit": commit, "sourceSha256": sha256_file(source)})
                write_json(root / "committer-status.json", {"status": "running", "lastStage": stage, "commit": commit})
                print(f"Committed stage {stage}: {commit}", flush=True)
            if (markers / "postprocess.json").exists():
                write_json(root / "committer-status.json", {"status": "complete", "commits": [read_json(p)
                                                           for p in sorted(markers.glob("*.json"))]})
                break
            if args.once:
                break
            time.sleep(30)
    except Exception as error:
        write_json(root / "committer-status.json", {"status": "failed", "error": f"{type(error).__name__}: {error}"})
        raise


if __name__ == "__main__":
    main()
