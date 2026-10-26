# Favorite threshold: development vs test clarification

## Request and constraints

The user identifies the existing-model point with maximum precision at recall >=90% as the current favorite and asks whether the previously quoted metrics were test metrics. No new training or experiments are requested. Preserve the local-commit/no-push workflow in `scoring_model`.

## Finding

Favorite candidate: current `sba-scoring-v1` with `p >= 0.15283707537791144`. This records a research preference; it does not activate a runtime policy.

The quoted precision 55.80%, F1 0.6889 and recall 90.01% came from FY2017 **calibration/development**, where the threshold was selected. FY2017 also fitted the sigmoid calibrator, so this is not an independent test result.

The identical, fixed threshold already has saved evaluation results:

| Cohort | Rows | Write-offs | Precision | F1 | Recall | TP | FP | FN |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| FY2017 calibration/development | 43,456 | 3,952 | 0.5579607843137255 | 0.6888738258932894 | 0.9000506072874493 | 3,557 | 2,818 | 395 |
| FY2018–2019 test | 60,186 | 5,927 | 0.4360851063829787 | 0.5797363806075692 | 0.8645183060570272 | 5,124 | 6,626 | 803 |
| FY2020–2026 transfer | 72,450 | 6,620 | 0.3798425840744148 | 0.4530878497835762 | 0.5613293051359517 | 3,716 | 6,067 | 2,904 |

All three metrics in each row use that one threshold. Neither test nor transfer achieves the desired recall >=90% and precision >=60%. These are historical saved benchmark results, not a fresh external validation.

## Sources and actual verification

- Read `fastapi/experiments/sba-scoring-retraining-plan-v1/current-model-business-targets.json`, specifically `bestPrecisionAtRecallFloor` and its calibration provenance.
- Read the previous `selection.json` and `evaluation.json` in `fastapi/experiments/sba-scoring-recall-thresholds-v1/`.
- A read-only Python extraction printed the identical threshold and complete precision/F1/recall/count rows for `maximum_f1_recall_ge_0.9` on calibration/test/transfer. The point exactly matches the user's selected favorite.
- Inspected Git status: existing unrelated upload report/index change and model `.DS_Store` remain outside task commits.
- No new predictions, model training, threshold search, or software tests were run; this task verifies saved evidence only.

## Changes and impacts

This new report and its shared index entry only. No model, policy, API, database or migration changes. No experimental metrics fabricated or averaged.

## Git

Initial HEAD `7446ba5`, branch `scoring_model`. This clarification is saved in its own local documentation commit. No push; unrelated working-tree changes preserved.
