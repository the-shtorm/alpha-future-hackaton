# Retraining strategy for recall >=90% and precision >=60%

## Request and constraints

- Propose a broad, concrete set of retraining heuristics and combinations for the current scoring model.
- Search decision thresholds separately for every fitted combination.
- Report precision, F1 and recall at the same optimal operating point, never averaged over thresholds or assembled from different thresholds.
- Target both recall >=0.90 and precision >=0.60. Select maximum F1 among feasible thresholds; do not claim success when the feasible set is empty.
- Continue the user's small-subtask/local-commit workflow in `scoring_model`, without push. Preserve the unrelated upload report/index changes and model `.DS_Store`.

## Subtasks

1. Inspect current model selection, available inputs, outcomes and temporal limitations — complete.
2. Research relevant supported training mechanisms in primary documentation — complete.
3. Define a large staged combination matrix and exact constrained threshold/reporting rules — in progress.
4. Save the proposal, executable threshold-selection helper and checks, and commit locally — pending.

## Findings

- Current `train.py` chooses among 32 configurations by validation Log Loss; it does not optimize the new dual constraint.
- Available scoring inputs: nine features, six categorical. Original snapshot is **2026-06-30** for every row; dates are available for approval and outcome. Recent FY2025/FY2026 counts are small (82/0 write-offs) in this completed-loan population.
- Current model's exact FY2017 curve has **zero** thresholds satisfying both requested floors.
- Maximum recall at precision >=60% on FY2017: precision **0.6000348554**, recall **0.8712044534**, F1 **0.7106295150**, threshold about **0.2106468479**.
- Maximum precision at recall >=90% on FY2017: precision **0.5579607843**, recall **0.9000506073**, F1 **0.6888738259**, threshold about **0.1528370754**.
- These are retrospective threshold-development measurements of the existing model, not retraining results or independent test metrics.
- At the requested boundary, F1 = 2*0.6*0.9/(0.6+0.9) = **0.72**. No candidate is promised to achieve it.

## Sources

- Repository: `fastapi/scoring_training/train.py`, `data.py`, existing threshold-search artifacts, dataset lock and `app/scoring/features.py`/`contracts.py`.
- https://catboost.ai/docs/en/concepts/parameter-tuning
- https://catboost.ai/docs/en/references/training-parameters/common
- https://catboost.ai/docs/en/concepts/python-reference_catboostclassifier_fit
- https://catboost.ai/docs/en/concepts/loss-functions-classification
- https://scikit-learn.org/stable/modules/classification_threshold.html
- https://scikit-learn.org/stable/modules/calibration
- https://lightgbm.readthedocs.io/en/stable/Parameters.html
- https://xgboost.readthedocs.io/en/stable/parameter.html
- https://imbalanced-learn.org/stable/over_sampling.html
- Read the `ml-pipeline-workflow` skill. Its optional referenced training/validation files were absent; primary documentation and repository evidence supply the needed detail. The already-read `hf-cli` skill covers the ML workflow; no remote Hub operations are required.

## Verification and deliverables

- Inspected Git status and the existing `scoring_model` branch.
- Read the previous exact development curve: zero feasible thresholds under both floors; computed the two boundary alternatives above.
- Read raw data's date columns and printed aggregate min/max/missing counts only; no loan records or personal data exported.
- No new model training has been performed in this proposal task. Planned candidate metrics will remain unfilled until measured.
- Added `fastapi/scoring_training/business_thresholds.py`: exact joint-feasibility selection, maximum F1 under both constraints, explicit infeasibility and two complete boundary alternatives. It does not average metrics or modify the previous experiment implementation.
- Added `test_business_thresholds.py`: same-threshold metrics checked against sklearn, joint vs separate constraint feasibility, tied scores, invalid floors and single-class rejection. **19 tests passed**; Ruff passed for both new files.

## Contract and migration impacts

None from the proposal or offline selector. Future feature changes, new targets, calibration formats, or new model families require explicitly versioned feature/model packages and serving adapters; they are proposed work, not implemented behavior.

## Git status

Initial HEAD `3a34f91`; initial unrelated working-tree changes preserved. Task commits pending; no push.
