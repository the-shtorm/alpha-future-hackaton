# Promote selected model5 to sba-scoring-v2

## Request and constraints

User explicitly requested making selected `mixed-v1-0051` the primary model and naming it `sba-scoring-v2`. Preserve the original favorite/backup, exact fitted model, calibration and frozen threshold0.167204479067272; no retraining or threshold tuning on validation. Small completed subtasks, local commits in scoring_model, no push. Preserve unrelated Hugging Face report/index changes and .DS_Store.

## Work in progress

Inspecting runtime package format, provenance checks, model lock, default paths, Compose and acceptance checks. The selected artifact uses original9/full NAICS, sigmoid calibration on FY2012 with random whole-year development splits. Runtime previously hard-coded FY2017 calibration. Plan: explicit pinned calibration provenance while retaining legacy compatibility, native CatBoost package export/replay, then primary defaults/lock and end-to-end API checks.

No schema/database migrations planned. Financial decision policy uses probability with its own boundaries; the selected research operating point will be preserved explicitly without silently changing the financial policy.

## Initial verification and limitations

Selected source checksums and FY2023 metrics were verified in the preceding selection task. Existing repository tests cover package integrity and real tiny models. Main Compose inspection currently cannot interpolate because RECSYS_API_KEY is not configured; no .env files were found. No deployment or Docker restart has been performed. Historical FY2023 quality is not a new independent test; desired85/55 remains unmet and TermInMonths historical availability is unconfirmed.

## Stage1: runtime provenance support

Added optional pinned calibrationYears and operatingThreshold to the existing manifest format. Legacy packages still require FY2017; explicitly pinned packages can use their actual calibration years. Mismatched/reversed/malformed year ranges are rejected. Prediction and response semantics are unchanged. Real tiny logistic/CatBoost package tests verify legacy integrity and explicit FY2012 provenance:35 tests passed in12.92s. Ruff import grouping differs between the nested training and main project configurations; verification uses the explicit main fastapi/pyproject.toml configuration. Docker daemon socket is absent, so container execution is unavailable in this session.

## Stage2: native package export

Added `scoring_training/promote_selected.py`: verifies the user-selected snapshot, frozen selection SHA, full dataset cache SHA and reconstructed role audits, copies native CatBoost and sigmoid parameters without fitting, builds applicability domain from actual fit rows, compares native probabilities/decisions against original joblib and stored predictions. Exported `models/sba-scoring-v2` with manifest/calibration/domain/training/evaluation and README; .gitignore/.gitattributes permit this version and LFS model while preserving v1/trial exclusions.

Actual export command from fastapi/: `OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 scoring_training/.venv/bin/python -m scoring_training.promote_selected`. Exit0, native replay passed on all9963 FY2023 rows, exact TP1211/FP843/FN517/TN7392 and precision0.5895813047711782/F1 0.6404019037546271/recall0.7008101851851852. Frozen threshold0.167204479067272 preserved; later historical FY2024–2026 metrics regenerated separately. Final package loaded through normal integrity/release checks; manifest SHA5d5498e8d3339ffbbce3d5f117f52692cee9986067a3bf6df8524c5e4c8c53ac. Demo release gates report technical replay and user selection, not85/55 achievement or a new independent test.
