# Random-row and random-year scoring experiment extension

## Request and constraints

The user explicitly selected **both** additional randomized splitting strategies: individual loans and entire fiscal years. Preserve the running full campaign, favorite `sba-scoring-v1` at threshold `0.15283707537791144`, local-only stage commits, and the resource limit of two active fits with two threads each and nice=10. Every fitted variant gets its own exact threshold search and precision/F1/recall at one operating point. Final top-10 selection and user-authorized cleanup must include the new variants.

## Scope and protocol

- Additional grid: 2 strategies ×3 split seeds (42/137/2026) ×3 feature bundles ×4 positive-class weighting modes (1/3/SqrtBalanced/Balanced) = **72 additional fits**. Model seed remains fixed at 42 so the split seed is an explicit separate variable.
- Historical pool: FY2010–2020 loans whose outcome was known strictly before **2022-10-01**. The existing cache/source hashes remain unchanged.
- Random rows: stratified, disjoint fit/early/calibration/threshold/historical-test roles, approximately 70/5/5/10/10%.
- Random years: 11 fiscal years permuted into seven fit years and one whole year for each of the other four roles. No fiscal year is shared between historical roles in this strategy.
- Both strategies keep **all FY2023 loans outside fitting, calibration and threshold search**. That existing historical validation cohort remains the only common basis for ranking against the favorite; it is not a new untouched external test.
- The randomized historical test is a separate diagnostic; its metrics cannot replace FY2023 metrics or satisfy the future-validation business goal by themselves. Do not compare the favorite on historical rows that it may have trained on.
- Existing completed-loan selection bias, possible borrower overlap and unconfirmed original loan-term availability remain limitations.

## Implementation and progress

- Added `fastapi/scoring_training/campaign_mixed.py`: split generation, explicit role audits, 72 configurations and a worker adapter reusing the already-tested fit/calibration/exact-threshold engine. Adds a separate historical-test measurement at the same frozen threshold.
- Extended `campaign_postprocess.py` to run the additional stage **after all existing base fitting pools finish**, before final ranking/cleanup. The currently running dispatcher imports this module only then, so no interruption or discarded fits is needed.
- Mixed fits reuse the shared bounded scheduler and `concurrency.json`, preserving two active fits and low priority. The original program is not replaced or shortened.
- Extended full CSVs and top-10 metadata with split strategy/seed and separate historical-test precision/F1/recall. FY2023 validation remains the final ranking basis.
- Added tests for disjoint rows/years, outcome-known cutoff, fixed FY2023 population, deterministic configuration count, future-label independence, real tiny fits for both strategies, frozen thresholds, cache reuse and serialized prediction replay.
- **Implemented, verified and queued.** After implementation commit `9330f7e`, atomically enabled `runs/recall90-precision60-campaign-v1/mixed-policy.json`, pinning that commit, the splitter SHA-256 and 72 configurations. `monitor-state.json` records the extension as queued. The current dispatcher will pick it up through its late postprocessing import. No full-data mixed-split fit has run yet; that execution remains part of the ongoing main campaign, not a completed result of this implementation task.
- Actual full-source audits for all six splits are saved in `mixed-protocol.json`: 316,208 historical rows /23,376 positives; common FY2023 validation 9,963 rows /1,728 positives. Random-row roles contain 221,345/15,810/15,810/31,621/31,622 loans (fit/early/calibration/threshold/historical-test). Random-year roles vary by seed; even the smallest held-out whole-year role has both classes (163 positives).
- The native campaign monitor was updated successfully to require both mixed strategies before final ranking/cleanup; no duplicate dispatcher or additional concurrency was started.

## Verification

- Before final naming clarification: 10 focused mixed-split tests passed in 1.89 seconds; Ruff passed.
- Raw input and current campaign state inspected read-only. Existing main campaign continues; current code changes do not alter its fitted-trial engine or pinned favorite package.
- Final full scoring-training suite: **281 passed in 6.99 seconds**. Command: `MPLCONFIGDIR=/tmp/alpha-scoring-mpl OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 scoring_training/.venv/bin/python -m pytest -c scoring_training/pyproject.toml scoring_training/tests` from `fastapi/`.
- `scoring_training/.venv/bin/python -m ruff check app/scoring scoring_training` and `git diff --check` passed. Existing configured scoring/data coverage is 98.76%; that percentage does not measure the new campaign modules.
- Tests include real tiny fits and a real spawned two-configuration mixed stage using a one-active-fit fixture limit, plus postprocess integration with the branch enabled/disabled. No full-source model-quality metrics are inferred from fixture tests.
- The frozen splitter and dataset-cache SHA-256 values match the audited protocol. Original favorite and independent backup both pass the actual `ScoringPackage` integrity loader.
- Read current primary progress: **400/480 screening records, zero failures**, still running at two active fits ×two threads; this is a checkpoint, not completion.

## Contract and migration impacts

Offline research only. No API/database/active model or threshold change. No new external dataset, paid GPU or increased CPU concurrency.

## Git

Initial HEAD `e8ad471`, branch `scoring_model`. Preserve the ongoing campaign report changes, unrelated Hugging Face report/index changes and `.DS_Store`. Implementation commit `9330f7e` contains both split branches, integration, tests and audited protocol. This report/index are finalized in a separate documentation commit after enabling the policy. No per-combination commits or push. The existing main campaign report remains in progress and is separately updated for later stage commits. Unrelated Hugging Face report/index changes and `.DS_Store` remain excluded.

## Remaining work

Implementation/queueing task complete. Actual 72 full-data fits, measured per-threshold metrics, final top-10 replay/retention, cleanup and final campaign report remain with the running parent campaign. The existing dispatcher (PID 44358) and stage committer (PID 45354) were both confirmed alive with nice=10 after enabling the extension.
