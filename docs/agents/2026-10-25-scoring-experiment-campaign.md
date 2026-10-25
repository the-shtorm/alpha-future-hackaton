# Executed scoring experiment campaign

## Request and constraints

- Execute the previously proposed retraining program, with an exact independent threshold search for each fitted candidate.
- Business target: recall >=90% and precision >=60%; report precision/F1/recall at the same operating point, never means over thresholds/folds.
- Preserve favorite `sba-scoring-v1`, threshold `0.15283707537791144`, original artifact hashes and recorded metrics. Keep runtime unchanged while experimenting.
- Small subtasks and local commits by completed stage, **not per combination**. No push. Preserve unrelated upload report/index work and `.DS_Store`.

## Progress

1. Audit original data, temporal feasibility and favorite preservation — complete.
2. Implement tested, restartable campaign runner and exact per-candidate reporting — screening/fitting implemented; composition/export in progress.
3. Execute screening, refinement, robustness, warm-start, competitors and ensembles — pending.
4. Compare actual operating points, export aggregate artifacts and finalize local commits — pending.

## Initial audit

- Initial branch `scoring_model`, HEAD `231123e`. Training runtime Python 3.11 and CatBoost are available; host reports 12 logical CPUs and 225 GiB free disk.
- Original CSV is local (33 MiB), SHA-256 pinned in the dataset lock. No remote dataset upload is required.
- LightGBM/XGBoost are not currently installed in the isolated scoring environment.
- The proposed consecutive-year point-in-time filter is statistically unusable: fold B threshold has 212 completed loans and only 2 write-offs known by the next fiscal year; fold C calibration has 330 loans and zero write-offs.
- Original strict annual cohorts: A early/calibration/threshold positives 4/6/6; B 6/5/2; C 2/0/3. No mass fitting on those threshold cohorts is justified.
- Execution protocol will explicitly version an adequate temporal gap, preserve outcome-known-before-validation filtering, and record the departure from the original proposal. Completed-loan-only selection bias and unconfirmed point-in-time term remain limitations.
- Execution protocol is now saved in `fastapi/experiments/sba-scoring-campaign-v1/protocol.json`: distinct fit/early/calibration/threshold approval periods with a common simulated fitting cutoff before validation. A/B/C validate FY2021/FY2023/FY2024; threshold roles contain 574/163/185 write-offs. Every development outcome must be known before the validation FY starts. This is a documented revision of the proposal, not silent reuse of future outcomes.
- `favorite.json` records exact original pin, file hashes, threshold and historical metric triplets. An independent copy in ignored `runs/recall90-precision60-campaign-v1/favorite-package` passes the same `ScoringPackage` integrity loader as the original.
- LightGBM 4.6.0 and XGBoost 3.0.5 installed with `--no-deps`, preserving original pinned core versions. Homebrew libomp installation was blocked by an unaccepted Xcode license; no license was accepted. Both packages successfully import using the existing scikit-learn bundled libomp via `DYLD_LIBRARY_PATH`.
- The 480 proposed records contain 384 distinct training configurations on primary fold B because all-history and the 10-year window are identical. The runner records aliases rather than wasting duplicate fits; each alias keeps the same complete threshold result and model provenance.

## Verification and artifacts

- Read `AGENTS.md`, proposal JSON, training/features/threshold code, dataset/model pins, skill instructions and Git status.
- Ran read-only raw-date aggregation for temporal cohort sizes/classes; generated a SHA-pinned prepared campaign cache in ignored runs/.
- New `campaign_data.py`: source/prepared alignment, common-cutoff cohort filtering, normalized recency weights, train-only safe/research feature bundles.
- New `campaign_fit.py`: actual model fitting for five families, separate sigmoid fitting, exact business threshold search, persisted selection before validation scoring, immutable favorite paths, saved research models/predictions and failure/resume records.
- New `campaign.py`: deterministic 480-record screening, conditional 360 refinements, competitors, warm-starts, seed/fold validation, process scheduling and durable progress; completed aliases preserve provenance.
- Initial fitted-trial checks found two test harness mistakes (duplicated LightGBM verbosity and omitted categorical metadata in prediction replay); both corrected. All five actual model families then passed tiny fit/serialization/restart checks.
- Focused campaign tests: 15 passed; Ruff passed. Checks cover leakage, temporal boundaries, all five fitted families, exact freeze/replay, 480/384 counts and feasible-F1 ranking.
- First full-data pilot (`screen-0000`, original9, fold B) completed in 58.49 seconds. At threshold 0.04403200656380213: development precision/F1/recall = 0.108247/0.193294/0.901840; fixed FY2023 validation = **0.452911/0.520669/0.612269**. Target not reached; pilot provenance retained separately from official versioned screening IDs.
- Report will be maintained during execution. Previous completed reports and proposals are immutable.

## Contract and migration impacts

Offline experiments only. Feature variants are research artifacts; no API, database, model lock or runtime policy changes are authorized by this campaign itself.

## Git

Stage commits pending. Original unrelated working-tree changes remain excluded. No push.
