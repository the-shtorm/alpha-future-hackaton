# User selection: model 5 / mixed-v1-0051

## Request and scope

User selected model5 from the completed campaign's final fallback top10: `mixed-v1-0051`. Record the exact choice, preserve a separate local artifact, verify it, and commit locally in `scoring_model` without push. Original favorite and backup remain untouched; runtime activation is not part of this selection. This is a new task report; completed campaign reports remain unchanged.

## Selected model and artifacts

- CatBoost, original9 feature bundle, Balanced class weighting, model seed42; random whole-year split with split seed137. Includes TermInMonths with unconfirmed historical availability.
- Frozen policy `bestPrecisionAtRecallFloor`, threshold **0.167204479067272**; no threshold search or new training during this task.
- FY2023 historical validation:9963 loans,1728 write-offs; **precision58.958130%, F1 64.040190%, recall70.081019%**. TP1211, FP843, FN517, TN7392.
- Versus original favorite on identical rows: precision+9.863693pp, F1+17.674888pp, recall+26.157407pp. Desired85/55 and tolerated84/53 remain unmet.
- Tracked selection manifest: `fastapi/experiments/sba-scoring-campaign-v1/selected-model.json`; export hash inventory updated. Existing top10 order/results unchanged.
- Independent ignored local snapshot: `fastapi/models/sba-scoring-selected-mixed-v1-0051/`, containing model.joblib, original result.json, frozen selection.json and selected-model.json. Original retained trial remains available.
- Model SHA256: `1df3fa6e9e5579889c1aa83c133c55b946e36664fb82cce28b891f5793a26cce`.

## Actual verification

Used `fastapi/scoring_training/.venv/bin/python` with OMP/BLAS/MKL limited to2 threads. Loaded the copied serialized artifact with `campaign_postprocess.artifact_probability` and replayed the exact retained FY2023 cohort: all labels/indices, probabilities (rtol1e-10/atol1e-12), confusion counts and precision/recall/F1 matched. Copied model and frozen selection checksums matched the source. Verified every pinned file and manifest of the original favorite and independent backup; all passed. Verified all33 exported hash entries, including the new selection manifest.

`git check-ignore` confirms the independent binary snapshot is excluded. `git diff --check` passed. No full test suite or additional training was needed for this metadata/copy-only task. No API, database, contract or migration changes.

## Limitations and Git

FY2023 is previously inspected historical validation, not a new independent test. Existing diagnostics at the same threshold show weaker later cohorts: FY2024 precision37.252619%, F1 43.272481%, recall51.612903%; FY2025 precision3.433476%, F1 5.079365%, recall9.756098%; FY2026 has0 positives, so recall is undefined. These diagnostics were read, not recomputed in this task.

The campaign joblib includes its feature builder and sigmoid calibrator and depends on the offline training modules. It is not yet converted to runtime `sba-package-1`; selecting it does not activate it. Original active package/threshold and backup are unchanged. Completed selection recorded in one local commit, no push. Unrelated Hugging Face report/index insertion and .DS_Store remain excluded from the commit.
