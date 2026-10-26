# Final scoring campaign and fallback execution

## Request and constraints

Execute all experiments, preserve the original favorite, optimize write-off recall, aim85% recall/55% precision with84%/53% tolerance. User additionally requested up to10 substantial improvements if targets remain unmet. Exact per-candidate frozen thresholds, all precision/F1/recall at one point, no averaging, model seed42, identical FY2023 cohort. CPU2 active fits ×2 threads/nice10; local commits only, no push. No automatic deployment.

## Full executed program

- Screening480 records (384 distinct fits), refinement360, competitors168, warm24, robustness90, mixed72, recent-holdout200, calibration20 and blends75: **1489 records**, **1288 distinct base model artifacts**, **0 failures**. Reused aliases/robustness fits were not counted as new training.
- Both shuffle strategies and all72+200 additional attempts completed. Source/prepared data and four core fit/cache modules stayed pinned. Existing completed master/implementation reports are preserved.
- Neither85/55 nor84/53 was reached on the common FY2023 validation. No thresholds were searched or changed using validation labels. This is historical/adaptive validation, not a fresh external test.
- Original completed target-only exports are preserved as`target-only-*`. The final status is **complete_with_subtarget_improvements**, not target achievement.

## Substantial fallback selection

Documented heuristic (not a user-supplied numeric formula): no precision/recall/F1 regression vs favorite, recall gain>=10 percentage points, F1 gain>=5 points. Rank by recall, then precision/F1; same binary decisions occupy one slot. All10 selected candidates exceed the baseline on all three metrics. Every selected model is original9 and includes TermInMonths with unconfirmed historical availability; these remain research candidates.

Baseline FY2023:9963 loans/1728 write-offs, t=0.15283707537791144, precision49.094437%, F1 46.365302%, recall43.923611% (TP759/FP787/FN969).

| Rank | Candidate | Threshold | Precision | F1 | Recall | ΔRecall pp | ΔPrecision pp | ΔF1 pp |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | refine-0036 | 0.043127688704757465 | 49.191959% | 58.522860% | 72.222222% | +28.298611 | +0.097522 | +12.157558 |
| 2 | refine-0015 | 0.051066381013790178 | 51.614256% | 59.858984% | 71.238426% | +27.314815 | +2.519819 | +13.493681 |
| 3 | warm-0005 | 0.037145512924654255 | 50.308769% | 58.792398% | 70.717593% | +26.793981 | +1.214332 | +12.427096 |
| 4 | refine-0027 | 0.07135383781983036 | 52.879581% | 60.298507% | 70.138889% | +26.215278 | +3.785144 | +13.933205 |
| 5 | mixed-v1-0051 | 0.16720447906727201 | 58.958130% | 64.040190% | 70.081019% | +26.157407 | +9.863693 | +17.674888 |
| 6 | screen-v1-0375 | 0.062320984836261285 | 58.036574% | 63.373621% | 69.791667% | +25.868056 | +8.942136 | +17.008318 |
| 7 | warm-0003 | 0.036028070089919567 | 49.979262% | 58.226625% | 69.733796% | +25.810185 | +0.884824 | +11.861322 |
| 8 | screen-v1-0306 | 0.039436790813159865 | 49.300412% | 57.623858% | 69.328704% | +25.405093 | +0.205974 | +11.258555 |
| 9 | screen-v1-0348 | 0.044320280398688745 | 53.605016% | 60.439283% | 69.270833% | +25.347222 | +4.510578 | +14.073981 |
| 10 | screen-v1-0477 | 0.042287004418359544 | 51.110162% | 58.820639% | 69.270833% | +25.347222 | +2.015725 | +12.455336 |

## Transfer limitations

At the SAME frozen leader0036 threshold, FY2024 precision/F1/recall=29.780309%/39.588967%/59.032258%; FY2025=5.487805%/8.780488%/21.951220%. Performance is not stable across later cohorts. FY2026 has83 completed loans/0 positives: recall undefined, never claimed0% risk. Completed-loan selection bias and possible borrower overlap remain. No model/threshold activated in the API; original package/backup unchanged.

## Actual verification and retention

- Full suite318 passed in10.57s; final8 focused fallback checks passed in1.61s after checkpoint repair addition. Existing configured scoring/data coverage98.76% does not measure new campaign modules. Ruff and whitespace checks passed.
- Real final command: `MPLCONFIGDIR=/tmp/alpha-scoring-mpl OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 scoring_training/.venv/bin/python -m scoring_training.campaign_fallback --apply`, from`fastapi/`, with nice10. Exit0.
- Main session42195 and committer29113 exited0 after full completion. Stage-committer final original commit1943d76. Fallback implementation4087f0c. Main training was never restarted for fallback and no extra full-data fit was run.
- Independently verified all1489 CSV rows, all72+200 status records,10 distinct decision masks, exact same FY2023 indices/labels, selected frozen threshold/selection SHA, exact precision/F1/recall, all retained model/dependency SHAs, replay ledger, every exported artifact hash, original and backup through actual ScoringPackage loader.
- Serialized replay passed for all10 before deletion. Retained10 model files and10 prediction archives, plus original favorite/backup outside trials. Deleted **2748** other weight/prediction files, freed **5259254486 bytes** (~5.26GB). All aggregate configs/metrics preserved.
- Visually inspected the actual generated plot. Fixed fiscal-year ticks to integers, re-rendered and refreshed export hashes; this reversible presentation fix did not change model/threshold/metrics. No new plotting unit test was needed.

## Artifacts and Git

`fastapi/experiments/sba-scoring-campaign-v1/`: top10.csv/json, fallback-results/summary/report, target-only backups, retention.json, full trials/operating-points, mixed/recent outputs, fixed-future-diagnostics, plot and artifact-hashes.json. Weights/predictions remain local/ignored. This NEW execution report and current aggregate artifacts are committed locally; completed master report is not overwritten. Unrelated Hugging Face report/index insertion and.DS_Store stay excluded. No push.

All research/fallback verification work complete. Native recurring monitoring is removed as the final completion step; its outcome is recorded in local monitor-state and the user response.
