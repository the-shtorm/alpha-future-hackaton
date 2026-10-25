# Recall90 filter followed by maximum precision

## Confirmed request

After rejecting two misinterpretations, the user explicitly selected: **“Recall ≥90% как фильтр; среди прошедших — максимальный precision.”** Therefore recall90% is the eligibility gate; precision60% remains a target, not a gate; ties prefer recall then F1. Main purpose is to improve the preserved favorite on the identical cohort, with all metric regressions disclosed. No automatic model replacement.

## Changes

- `campaign_priority.py`: shared recall90%-eligibility and precision/recall/F1 ordering.
- `campaign_retention.py`: candidates below recall90% are excluded, not silently used as fallback winners. Improvement qualification follows this objective; deduplication/replay/dependency/favorite protections remain. If none qualify, selection is empty and finalization/cleanup refuses to proceed.
- `campaign_postprocess.py`: final top-10 and safe winner follow the confirmed rule. Maximum F1 and old constraint proximity are separate diagnostics. Top10 CSV contains deltas for all three metrics, target flags, dominance and tradeoff flags relative to the unchanged favorite.
- `campaign_recent_holdout.py`:100-parent source shortlist and historical-validation finalists use the same recall filter and maximum precision. Its200-fit shortlist has not been generated, so the pending code/hash can safely advance before the first full-data fit. Data/class-sufficiency audits unchanged.
- README/protocol/monitor updated. Existing base search/parents and frozen primary thresholds stay unchanged; no validation threshold tuning, cached model mutation, core fit/cache-hashed module edit, duplicate dispatcher or CPU increase.

## Actual verification

Final full-suite/lint/checksum/enablement results recorded below. Tests prove recall below90% cannot beat recall90% despite high precision/F1; among qualifying rows higher precision wins over higher recall, with no precision60% gate; a lower-F1 tradeoff remains visible; an empty eligible set stays empty. Same rule is checked for source100 and historical-only shortlists.

## Git and contracts

Offline selection only. Local commit `a512bbd` encoded an earlier rejected precision-floor interpretation; the confirmed implementation supersedes it below. Initial favorite/package/backup, active API/database and no-push constraints remain unchanged. Preserve unrelated report/index edits and .DS_Store.


## Verified outcome

- Final full scoring-training suite: **297 passed in8.76s**, command from `fastapi/`: `MPLCONFIGDIR=/tmp/alpha-scoring-mpl OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 scoring_training/.venv/bin/python -m pytest -c scoring_training/pyproject.toml scoring_training/tests`. Ruff (`app/scoring scoring_training`) and `git diff --check` passed. Existing configured scoring/data coverage98.76% does not measure new campaign modules.
- During adaptation, one old test still expected three improvements including a recall<90% candidate (296 passed/1 failed). Corrected its expectation to two eligible rows; full final run above passed. Earlier rejected-order checks are not evidence of the final contract.
- Implementation commit **`e80cafa`** supersedes `a512bbd`. Atomically advanced the enabled200-fit policy to the new module/ranking hashes and implementation commit before its shortlist/first full-data fit; updated retention policy and monitor metadata to the confirmed rule.72-fit policy unchanged. Native monitor updated successfully; user10-minute interval preserved.
- Original favorite and backup both pass `ScoringPackage` integrity. Same FY2023 population and saved threshold checksum verified for the current conditional leader `refine-0241`, t=0.04497684248442092: precision/F1/recall **0.246927/0.388160/0.906829**. It meets recall90% while precision and F1 are BELOW the favorite, so this is a **tradeoff, not dominance**. Precision60% goal remains unmet. This distinction is retained in metadata; no model activation.
- Current base checkpoint278/360 refinement records, zero failures; main session42195 and stage-committer25712 confirmed live. No restart/extra dispatcher or load increase. No new full-data fit was needed for this ranking correction; all pending fits still required.
- Implementation/queue-policy task complete. Future training, final comparison/replay/retention and final campaign report remain with the running parent campaign. This report/index finalized in its own local documentation commit; unrelated upload/index work and .DS_Store excluded; no push.
