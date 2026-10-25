# Executed scoring experiment campaign

## Request and constraints

- Execute the previously proposed retraining program, with an exact independent threshold search for each fitted candidate.
- Business target: recall >=90% and precision >=60%; report precision/F1/recall at the same operating point, never means over thresholds/folds.
- Preserve favorite `sba-scoring-v1`, threshold `0.15283707537791144`, original artifact hashes and recorded metrics. Keep runtime unchanged while experimenting.
- Small subtasks and local commits by completed stage, **not per combination**. No push. Preserve unrelated upload report/index work and `.DS_Store`.

## Progress

1. Audit original data, temporal feasibility and favorite preservation — complete.
2. Implement tested, restartable campaign runner and exact per-candidate reporting — complete.
3. Execute screening, refinement, robustness, warm-start, competitors and ensembles — in progress.
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
- Implemented `campaign_postprocess.py`: independent calibration branches, row-aligned ensemble predictions, per-point metrics, portable CSVs, fixed future/favorite comparisons, safe-vs-original feature leaders and static figure. Added dedicated composition, alignment, byte-normalization and end-to-end export tests.
- Full scoring-training suite: **259 passed in 24.26 seconds**, Ruff and diff whitespace check passed. Existing configured scoring/data coverage 98.76%; this percentage does not measure new campaign modules. A subsequent extra end-to-end postprocessing test is verified separately.
- After user questioned GPU usage, verified `Darwin arm64`, no `nvidia-smi`, and CatBoost GPU count 0. Official CatBoost wheel support table confirms no macOS CUDA training: https://catboost.ai/docs/en/installation/python-installation-method-pip-install?lang=en.
- User explicitly chose local CPU execution at lower load, then allowed 2–3 simultaneous fits. Original six-fit dispatcher was stopped; all completed results preserved. Current setting: **2 active fits, 2 threads each, nice 10**. Parent pool can host 3 workers but bounded submission and live `concurrency.json` limit active jobs to two; full search volume unchanged.
- Last recorded screening checkpoint before this report update: 86/480 records, zero failures; closest current FY2023 validation point precision/F1/recall **0.488206/0.565090/0.670718**, threshold **0.03942395810713749**. This is not a feasible 90/60 result or a final campaign winner.
- Resume regression tests detected alias-owner metadata cycles after a restart. The dispatcher now prefers the actual artifact owner, normalizes aliases and promotes each fitted signature once; no model metrics changed or completed fits were discarded.
- Added bounded live concurrency and regression coverage proving that reducing two active jobs to one does not lose queued trials.
- User requested improvement notifications even below target. Pinned `favorite-validation.json` proves identical FY2021/FY2023/FY2024 row/class counts for fair same-cohort comparisons. A 30-minute thread heartbeat named "Контроль экспериментов скоринга" was created and its automation card viewed successfully; unchanged states remain quiet.
- First announced improvement on FY2023: `screen-v1-0021`, threshold 0.04798450147360898, precision/F1/recall **0.545997/0.587323/0.635417**, vs favorite **0.490944/0.463653/0.439236**. Later announced `screen-v1-0093`, threshold 0.04756353377209248, **0.563609/0.608626/0.661458**. Both are original9 research variants with unconfirmed historical term; neither meets 90/60.
- User explicitly authorized keeping final top-10 and deleting other trial weights. Implemented `campaign_retention.py`: goal-first/F1 ranking of distinct improved decision vectors; all retained models must replay exact decisions before cleanup; preserve ensemble dependencies, favorite and aggregate logs. Added replay-failure, path-boundary, dependency and deduplication tests.
- Added stage-only aggregate Git snapshots via `campaign_stage_commit.py`. Real temporary Git-repository tests prove unrelated staged content and the unrelated working shared-index addition are excluded and preserved.
- The nice wrapper was found to be sandbox-blocked; dispatcher/workers were explicitly lowered using authorized `setpriority`, and **all four current PIDs verified nice=10**. The Mac protected nice executable also stripped DYLD_LIBRARY_PATH, exposing two optional-competitor import failures in a full test run (266 passed/2 failed). Resolved using a same-inode hard link from the already installed sklearn libomp into the training Python base runtime, with no existing file overwritten; no campaign restart needed. Direct LightGBM/XGBoost imports now work without DYLD overrides; favorite and backup integrity still pass.
- Latest full verification after this fix: **268 passed in 5.64 seconds**; Ruff and `git diff --check` passed. Existing configured scoring/data coverage remains 98.76%; dedicated campaign tests cover the new modules.
- Latest recorded checkpoint: **223/480 screening records**, **127 distinct completed model artifacts**, zero model failures. Background execution remains in progress; no final top-10 is claimed yet.

- Monitoring checkpoint 2026-10-25 19:23 UTC: screening **419/480**, zero failures; main session 42195 and committer session 25712 remain live, mixed policy is enabled with its frozen code hash. No duplicate process was started. Favorite and backup pass `ScoringPackage` integrity. Newly announced precision-floor alternative `screen-v1-0381`, fixed t=0.0826965891311357, FY2023 9,963 rows/1,728 positives: precision/F1/recall **0.614075/0.620057/0.626157** (TP1082/FP680/FN646). All three exceed the original favorite; versus announced `0375`, precision is higher but F1 and recall are lower. Research original9 includes unconfirmed historical term; joint 90/60 target remains unmet. Frozen threshold selection SHA-256 verified; no model fitting or threshold tuning during this monitoring check.

- User status check 2026-10-25 22:25 Europe/Moscow: campaign did not stop. Primary/committer sessions both remain running; observed progress advanced from 419 to 432/480 screening records, zero failures, journal and console updated five seconds before inspection. Existing two-fit/two-thread control unchanged. No restart, new dispatcher, model change or per-check commit.

## Contract and migration impacts

Offline experiments only. Feature variants are research artifacts; no API, database, model lock or runtime policy changes are authorized by this campaign itself.

## Git

- `bc9638a` — favorite preservation, audited temporal protocol, fitted-trial engine and deterministic screening/stage scheduler.
- Composition/export and bounded CPU scheduler form the next implementation-stage commit. Original unrelated working-tree changes remain excluded. No push.
- Final retention, background notifications and stage-only private-index commits are implemented; stage-committer deployment follows its implementation commit. No per-combination commits or push.
- `e8ad471` — completed composition/export, verified top-10 retention/cleanup, bounded CPU scheduling and private-index stage commits. Stage-committer is running independently with verified nice=10; initial status records PID 45354. Native 30-minute thread monitoring is active. Implementation files are committed; subsequent report updates are captured by the next completed-stage commit.
- User selected **both random rows and random whole years**. Implemented/audited a 72-fit extension, executed by the existing dispatcher after base fitting and before final top-10/cleanup. FY2023 stays outside fit/calibration/threshold search; randomized historical test is separately reported at the same frozen threshold. See [extension report](2026-10-25-scoring-mixed-split-extension.md). No full-data mixed fit has run at this checkpoint.
- Extension verification: **281 tests passed in 6.99 seconds**, Ruff and whitespace checks passed; original favorite and backup integrity verified. The current screening checkpoint is **400/480 records, zero failures**. Latest announced FY2023 candidate `screen-v1-0375` at t=0.062320984836261285: precision/F1/recall **0.580366/0.633736/0.697917**, still below 90/60.

### Completed stage: screening

- 480 records; 384 distinct saved artifacts; 0 failed records. Exact per-point CSVs exported under `fastapi/experiments/sba-scoring-campaign-v1/stages/screening`.
- Fold B, largest measured fixed-threshold validation F1: `screen-v1-0426`, threshold 0.082309165577004892, precision **0.665411**, F1 **0.638362**, recall **0.613426**.
