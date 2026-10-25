# Top-100 shuffled-history retraining with FY2020–2026 holdout

## Request and constraints

User explicitly approved **100 distinct configurations × two shuffle strategies =200 additional fits**, one split seed. Preserve the existing full program, favorite and backup, two active fits ×two threads, nice=10, local stage commits without push, final replay before cleanup. These are additional fits, not a replacement for the previously queued 72 mixed fits.

## Implemented protocol

- Candidate shortlist: top 100 distinct cold-fit configurations from the completed primary campaign, ranked goal-first then F1/recall/precision. No old model/checkpoint is carried into new fits; this prevents old future training labels from entering the new branch. Recalibrations/ensembles/warm checkpoints are excluded from the cold-fit shortlist.
- Historical development: FY2010–2019 and outcomeDate strictly before 2019-10-01 (FY2020 start). Separate fit, early stopping, calibration, threshold and historical validation roles; both random rows and disjoint whole years. Own exact threshold search for every new fitted candidate.
- All FY2020–2026 are excluded from those five roles. Evaluate the seven fiscal years separately and pooled by confusion counts at the same frozen threshold. No averages. Recall is undefined for years without positives.
- Existing source candidates were selected using previously inspected FY2023; this carryover shortlist and final FY2023 ranking make the later-year check an adaptive historical benchmark, not an untouched independent test.
- Final common top-10 remains on identical FY2023 cohort; keep separate historical-validation ranking as a diagnostic. No threshold is retuned on any later-year labels.
- Preliminary full-source audit: historical pool 191,134 loans /14,745 write-offs. FY2019 alone has only five eligible write-offs; whole-year role assignment must enforce sufficient class counts instead of silently accepting a five-positive calibration cohort.

## Implementation and verification

- Added `fastapi/scoring_training/campaign_recent_holdout.py`: exact top-100 configuration deduplication and frozen shortlist; no transferred checkpoints; supported row/year splitting; shared bounded process scheduler; per-fit threshold freeze; separate historical validation, each later year and pooled metrics. New fits retain their own window/recency/class/hyperparameter settings.
- `campaign_postprocess.py` now calls this branch after the previous 72 mixed fits and before final top-10, replay and cleanup. It preserves the existing FY2023 ranking contract, includes all new results in aggregate tables and includes their historical/later-year details in top-10 metadata. No running base worker or core cache-hashed training module was modified.
- Partial base fits are persisted as `pending_future_evaluation`, never as a cacheable complete holdout result. Evaluation failures become explicit failed records, with original worker functions restored. An unavailable 100-parent shortlist raises an error instead of silently shortening the approved program.
- User additionally authorized random split corrections for class sufficiency. Whole-year assignments are deterministically resampled on historical class counts until every role (including fit after its window) has >=100 observations of each class. Random rows are stratified. Maximum1,000 attempts; record seed and actual attempt count; failure remains explicit.
- Full-source audits for all eight strategy/window combinations are in `recent-holdout-protocol.json`. Both schemes have sufficient classes. Whole-year assignment accepted attempt2; its calibration has1,626 positives and threshold3,117. Even the smallest three-year fit has213 positives. Random-row calibration has737 positives and threshold/validation1,475 each.
- Later-year pool has72,450 loans /6,620 positives. FY2026 has83 loans /0 positives; recall is undefined, not a successful90% result.
- Native monitor successfully updated to require all200 attempts and the new exports before final cleanup/completion, preserving the user-edited10-minute interval. No duplicate automation or dispatcher.
- **Implemented, tested and queued.** After implementation commit `a28d2a8`, atomically enabled `recent-holdout-policy.json` with100 parents/200 fits, the frozen implementation hash and pre-2020 cutoff. `monitor-state.json` records queued execution. No full-data model fit for this new branch has run yet; the live dispatcher's late import will include it without restarting completed work.

### Actual checks

- Initial focused run:10 passed/1 failed due to a test fixture passing a string instead of `Path` to the existing hash helper; corrected. Subsequent focused holdout/postprocess suite:19 passed in3.07s. Ruff then identified three style issues; corrected before final verification.
- Final command from `fastapi/`: `MPLCONFIGDIR=/tmp/alpha-scoring-mpl OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 scoring_training/.venv/bin/python -m pytest -c scoring_training/pyproject.toml scoring_training/tests` — **294 passed in8.92s**. Tests cover disjoint roles, future-label/outcome invariance, sufficient-class random correction, exactly200 distinct configurations, cached frozen shortlist, real tiny fits for both schemes, serialized replay on every year/pooled block, zero-positive recall, interrupted evaluation, real spawned branch and final-hook integration.
- `scoring_training/.venv/bin/python -m ruff check app/scoring scoring_training` and `git diff --check` passed. Configured scoring/data coverage98.76% does not measure the new campaign modules.
- Original favorite and independent backup both passed the actual `ScoringPackage` integrity loader. Frozen implementation/cache hashes match the audited protocol. No new model-quality result is inferred from fixture tests.

## Contract and Git

Offline training only; active package/API/database unchanged. Work on scoring_model; preserve unrelated Hugging Face report/index work and .DS_Store. No push.

## Completion boundary

This implementation/queueing task is complete. The200 full-data attempts, measured model-quality results, final common top-10/replay and cleanup remain part of the running parent campaign. Implementation commit `a28d2a8`; this report and its index entry are committed after policy enablement. Existing unrelated files remain excluded.
