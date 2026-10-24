"""Local E5 adaptation of the train-sentence-transformers production training template."""
# ruff: noqa: E402

import argparse
import importlib.metadata
import json
import logging
import os
import time
from contextlib import nullcontext
from pathlib import Path

os.environ.update(
    HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", TOKENIZERS_PARALLELISM="false", HF_HUB_DISABLE_TELEMETRY="1"
)

import torch
from datasets import Dataset
from sentence_transformers import (
    SentenceTransformer,
    SentenceTransformerModelCardData,
    SentenceTransformerTrainer,
    SentenceTransformerTrainingArguments,
)
from sentence_transformers.sentence_transformer.evaluation import SentenceEvaluator
from sentence_transformers.sentence_transformer.losses import OnlineContrastiveLoss
from transformers import EarlyStoppingCallback, set_seed

from app.core.config import ROOT
from app.services.encoder import verify_manifest
from scripts.calibrate import digest, load_data
from scripts.finetune_utils import (
    labeled_pairs,
    mine_pairs,
    ranking_summary,
    score_model,
    validate_split_isolation,
    write_model_manifest,
)


def autocast_ctx():
    return (
        torch.autocast("cuda", dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16)
        if torch.cuda.is_available()
        else nullcontext()
    )


class ProfileEvaluator(SentenceEvaluator):
    def __init__(self, catalog, scenarios):
        self.catalog, self.scenarios = catalog, scenarios
        self.primary_metric, self.greater_is_better = "dev_average_precision", True

    def __call__(self, model, output_path=None, epoch=-1, steps=-1):
        values = ranking_summary(score_model(model, self.catalog, self.scenarios))
        logging.info(
            "development step=%s AP=%.4f NDCG@3=%.4f", steps, values["average_precision"], values["ndcg_at_3"]
        )
        return {"dev_" + k: v for k, v in values.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "models/e5-credit-finetune-v1")
    parser.add_argument("--push-to-hub", default=None, help="Only with explicit publication authorization")
    cli = parser.parse_args()
    smoke = cli.smoke or os.getenv("SMOKE_TEST") == "1"
    output = cli.output.resolve()
    if (output / "training-summary.json").exists():
        raise FileExistsError("Use a new directory for a new experiment")
    logdir = output / "logs"
    logdir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        format="%(asctime)s - %(message)s",
        level=logging.INFO,
        handlers=[logging.StreamHandler(), logging.FileHandler(logdir / "e5-credit.log", encoding="utf-8")],
        force=True,
    )
    for name in (
        "httpx",
        "httpx2",
        "httpcore",
        "httpcore2",
        "huggingface_hub",
        "urllib3",
        "filelock",
        "fsspec",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA required; CPU fallback is disabled")
    torch.set_float32_matmul_precision("high")
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    set_seed(20261024)
    os.environ.update(
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        TOKENIZERS_PARALLELISM="false",
        HF_HUB_DISABLE_TELEMETRY="1",
    )
    start = time.perf_counter()
    catalog, _, _ = load_data()
    groups = validate_split_isolation()
    training = groups["train"][:12] if smoke else groups["train"]
    development = groups["development"][:12] if smoke else groups["development"]
    lock = json.loads((ROOT / "config/model.lock.json").read_text(encoding="utf-8"))
    verify_manifest(ROOT / "models/multilingual-e5-small", lock["revision"])
    model = SentenceTransformer(
        str(ROOT / "models/multilingual-e5-small"),
        device="cuda",
        local_files_only=True,
        trust_remote_code=False,
        model_card_data=SentenceTransformerModelCardData(
            language="ru", license="mit", model_name="Local E5 credit-semantics experiment"
        ),
    )
    model.max_seq_length, model.default_prompt_name, model.prompts = 512, None, {}
    logging.info(
        "GPU=%s train_profiles=%d dev_profiles=%d dtype=%s",
        torch.cuda.get_device_name(0),
        len(training),
        len(development),
        next(model.parameters()).dtype,
    )
    pairs, audit = mine_pairs(model, catalog, training)
    (output / "mining-audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (output / "training-pairs.jsonl").open("w", encoding="utf-8") as stream:
        for row in pairs:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    train_dataset = Dataset.from_list(pairs).select_columns(["query", "passage", "label"])
    eval_dataset = Dataset.from_list(labeled_pairs(catalog, development)).select_columns(
        ["query", "passage", "label"]
    )
    evaluator = ProfileEvaluator(catalog, development)
    with autocast_ctx():
        baseline_eval = evaluator(model)[evaluator.primary_metric]
    before = model[0].auto_model.encoder.layer[-1].attention.self.query.weight.detach().clone()
    bf16 = torch.cuda.is_bf16_supported()
    args = SentenceTransformerTrainingArguments(
        output_dir=str(output / "checkpoints"),
        num_train_epochs=2,
        max_steps=1 if smoke else -1,
        per_device_train_batch_size=16,
        per_device_eval_batch_size=16,
        learning_rate=2e-5,
        weight_decay=0.01,
        warmup_steps=0.1,
        lr_scheduler_type="linear",
        bf16=bf16,
        fp16=not bf16,
        tf32=True,
        optim="adamw_torch",
        eval_strategy="steps",
        eval_steps=1 if smoke else 0.25,
        save_strategy="steps",
        save_steps=1 if smoke else 0.25,
        save_total_limit=2,
        save_only_model=True,
        load_best_model_at_end=True,
        metric_for_best_model=f"eval_{evaluator.primary_metric}",
        greater_is_better=True,
        logging_steps=1 if smoke else 0.05,
        logging_first_step=True,
        report_to="none",
        run_name="e5-credit-v1",
        seed=20261024,
        dataloader_num_workers=0,
        dataloader_pin_memory=True,
        disable_tqdm=True,
        push_to_hub=False,
    )
    trainer = SentenceTransformerTrainer(
        model=model,
        args=args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        loss=OnlineContrastiveLoss(model, margin=0.5),
        evaluator=evaluator,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=3)],
    )
    trainer.train()
    with autocast_ctx():
        score = evaluator(model)[evaluator.primary_metric]
    delta = score - baseline_eval
    verdict = "WIN" if delta >= 0.005 else "MARGINAL" if delta >= 0 else "REGRESSION"
    changed = torch.linalg.vector_norm(
        model[0].auto_model.encoder.layer[-1].attention.self.query.weight.detach() - before
    ).item()
    final = output / "final"
    model.save_pretrained(str(final), safe_serialization=True)
    manifest = write_model_manifest(
        final,
        {
            "localModelId": "local/e5-credit-finetune-v1",
            "baseModelId": lock["modelId"],
            "baseRevision": lock["revision"],
            "labelStatus": "SYNTHETIC_PROPOSED",
            "trainDatasetSha256": digest(ROOT / "evaluation/finetune-train.json"),
            "trainingPairsSha256": digest(output / "training-pairs.jsonl"),
            "maxSeqLength": 512,
            "dimension": 384,
            "trainSteps": trainer.state.global_step,
            "seed": 20261024,
        },
    )
    summary = {
        "verdict": verdict,
        "baselineDevAP": baseline_eval,
        "fineTunedDevAP": score,
        "deltaDevAP": delta,
        "weightDeltaL2": changed,
        "trainProfiles": len(training),
        "trainPairs": len(pairs),
        "positivePairs": sum(r["label"] == 1 for r in pairs),
        "steps": trainer.state.global_step,
        "bestCheckpoint": trainer.state.best_model_checkpoint,
        "bestDevAP": trainer.state.best_metric,
        "durationSeconds": time.perf_counter() - start,
        "gpu": torch.cuda.get_device_name(0),
        "peakAllocatedVramBytes": torch.cuda.max_memory_allocated(),
        "artifactSha256": manifest["artifactSha256"],
        "versions": {
            n: importlib.metadata.version(n)
            for n in ("torch", "transformers", "sentence-transformers", "datasets", "accelerate")
        },
        "trainingArguments": {
            "loss": "OnlineContrastiveLoss",
            "margin": 0.5,
            "learningRate": 2e-5,
            "epochs": 2,
            "batchSize": 16,
            "bf16": bf16,
        },
        "notice": "Local experiment. Calibration/final not used for optimization/checkpoint selection.",
    }
    (output / "training-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    logging.info(
        "VERDICT: %s | score=%.4f | baseline=%.4f | delta=%+.4f", verdict, score, baseline_eval, delta
    )
    logging.info("Saved local model; steps=%d weight_delta=%.6f", trainer.state.global_step, changed)
    if cli.push_to_hub and not smoke:
        try:
            model.push_to_hub(cli.push_to_hub)
        except Exception:
            logging.exception("Explicitly requested Hub publication failed")


if __name__ == "__main__":
    main()
