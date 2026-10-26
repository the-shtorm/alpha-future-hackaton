# Promote selected model5 to sba-scoring-v2

## Request and constraints

User explicitly requested making selected `mixed-v1-0051` the primary model and naming it `sba-scoring-v2`. Preserve the original favorite/backup, exact fitted model, calibration and frozen threshold0.167204479067272; no retraining or threshold tuning on validation. Small completed subtasks, local commits in scoring_model, no push. Preserve unrelated Hugging Face report/index changes and .DS_Store.

## Implementation scope

Inspected runtime package format, provenance checks, model lock, default paths, Compose and acceptance checks. The selected artifact uses original9/full NAICS, sigmoid calibration on FY2012 with random whole-year development splits. Runtime previously hard-coded FY2017 calibration. Implemented explicit pinned calibration provenance with legacy compatibility, native CatBoost export/replay, primary defaults/lock and real scoring API checks.

No schema/database migrations planned. Financial decision policy uses probability with its own boundaries; the selected research operating point will be preserved explicitly without silently changing the financial policy.

## Initial verification and limitations

Selected source checksums and FY2023 metrics were verified in the preceding selection task. Existing repository tests cover package integrity and real tiny models. Main Compose inspection currently cannot interpolate because RECSYS_API_KEY is not configured; no .env files were found. No deployment or Docker restart has been performed. Historical FY2023 quality is not a new independent test; desired85/55 remains unmet and TermInMonths historical availability is unconfirmed.

## Stage1: runtime provenance support

Added optional pinned calibrationYears and operatingThreshold to the existing manifest format. Legacy packages still require FY2017; explicitly pinned packages can use their actual calibration years. Mismatched/reversed/malformed year ranges are rejected. Prediction and response semantics are unchanged. Real tiny logistic/CatBoost package tests verify legacy integrity and explicit FY2012 provenance:35 tests passed in12.92s. Ruff import grouping differs between the nested training and main project configurations; verification uses the explicit main fastapi/pyproject.toml configuration. Docker daemon socket is absent, so container execution is unavailable in this session.

## Stage2: native package export

Added `scoring_training/promote_selected.py`: verifies the user-selected snapshot, frozen selection SHA, full dataset cache SHA and reconstructed role audits, copies native CatBoost and sigmoid parameters without fitting, builds applicability domain from actual fit rows, compares native probabilities/decisions against original joblib and stored predictions. Exported `models/sba-scoring-v2` with manifest/calibration/domain/training/evaluation and README; .gitignore/.gitattributes permit this version and LFS model while preserving v1/trial exclusions.

Actual export command from fastapi/: `OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 scoring_training/.venv/bin/python -m scoring_training.promote_selected`. Exit0, native replay passed on all9963 FY2023 rows, exact TP1211/FP843/FN517/TN7392 and precision0.5895813047711782/F1 0.6404019037546271/recall0.7008101851851852. Frozen threshold0.167204479067272 preserved; later historical FY2024–2026 metrics regenerated separately. Final package loaded through normal integrity/release checks; manifest SHA5d5498e8d3339ffbbce3d5f117f52692cee9986067a3bf6df8524c5e4c8c53ac. Demo release gates report technical replay and user selection, not85/55 achievement or a new independent test.

## Stage3: primary configuration and verification — completed

- Changed Settings default, primary scoring-model.lock.json, main/disposable Compose mounts and both .env examples to sba-scoring-v2. Preserved old pin separately as config/scoring-model-v1.lock.json; original package/backup file hashes all verified unchanged. Existing .env files were absent, so no secrets/configuration files were overwritten.
- Model-info now reports the pinned operatingThreshold. Evaluate contract remains sba-scoring-1 with probability p and score=round-half-up(100*(1-p)). No Java financial-policy changes, DB changes or migrations. The0.167204479067272 research threshold is not silently substituted for Java risk/PTI boundaries.
- Updated selection manifest/33-file campaign hash inventory, README, scoring/training documentation, rollback commands and full-stack acceptance script version/path/output defaults. Historical v1 benchmark files preserved. Independent selected research snapshot remains untouched and ignored.
- Actual checks: `RUN_SCORING_INTEGRATION=1 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 scoring_training/.venv/bin/python -m pytest --no-cov tests/api/test_scoring_api.py tests/integration/test_scoring_v2_package.py` from fastapi/: **16 passed in2.09s**, one Starlette httpx deprecation warning. Real native v2 scoring/lock/calibration/threshold through app startup, readiness/model-info/evaluate, score formula and demo warnings passed. Ranking used a test encoder (not a real E5 inference). Wrong-version package stayed unavailable instead of falling back; original v1 loaded with rollback pin.
- Full isolated scoring-training suite: `OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 .venv/bin/python -m pytest` from fastapi/scoring_training/: **320 passed in19.80s**. Configured scoring/data branch coverage **98.77%**; this does not measure exporter/campaign code coverage. Additional initial35-test run is a subset, not extra unique tests.
- Ruff using explicit fastapi/pyproject.toml and git diff --check passed. Docker Compose config parsed successfully with .env.example; default v2 read-only mount verified. Every primary package hash/lock, all33 campaign export hashes, favorite/backup hashes and committed v2 LFS pointer verified.
- Installed httpx/pydantic-settings/uvicorn only in the local isolated training venv for API checks; project dependency locks were not changed. No training jobs, GPU use, uploads or push.

## Completion and operational limit

Primary model in repository configuration is sba-scoring-v2; real package/API verification completed. Docker daemon is not running and root RECSYS_API_KEY is unset, so no full-stack v2 Docker deployment/benchmark was performed. Updated script is prepared for that future run; old v1 full-stack results are not presented as v2 results. No long-running API process was left running. The user can start the normal stack with their own environment configuration. Technical demo promotion does not establish85/55 or production banking validity.

Stage commits are local only:9cf9845 (provenance),51c2105 (native package), followed by the completed primary-configuration commit. Unrelated Hugging Face report/index insertion and v1 .DS_Store remain outside all task commits. All requested selection/packaging/default-switch work is complete.
