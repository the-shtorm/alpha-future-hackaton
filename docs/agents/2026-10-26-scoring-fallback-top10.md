# Final fallback top-10 of substantial favorite improvements

## Request

User restored monitoring to30 minutes and requested: if no clear85/55 (or accepted84/53) candidates are found, show up to10 distinct variants that substantially improve the preserved favorite, with recall emphasis. Full planned program, frozen thresholds, identical FY2023 cohort, resource limit2×2/nice10, local-only commits and replay-before-cleanup remain.

## Implemented workflow

Add a separate post-run fallback finalizer. The running main dispatcher need not restart or change its loaded final-selection code: its no-feasible branch preserves all weights. Only after the entire72+200 program and original stage commits finish can the new step select/replay/export fallback candidates and perform user-authorized retention. Preserve target-only exports as backups, completed master report unchanged, and label subtarget improvements clearly.

Operational definition of substantial (documented heuristic, not user-supplied numeric limits): precision/recall/F1 must not regress vs the same-cohort favorite, recall gain>=10 percentage points and F1 gain>=5 points. Rank fallback by recall, then precision and F1; deduplicate identical decisions. Never pad with weaker rows. Target-feasible candidates take precedence; fallback cannot overwrite them. If no substantial improvement, all weights remain preserved.

## Progress and verification

Added `campaign_fallback.py` and dedicated tests. Native30-minute interval verified in saved TOML; local metadata and README synchronized. Original target-only exports are backed up; completed main task report remains immutable. CLI requires all original and72+200 attempt counts, completed original committer, empty target top-10, frozen thresholds/cohort and preserved original weights; it refuses target-qualified results. Subtarget metadata and report explicitly state target failure. Same `retain_top_models` proof/dependency logic is used before cleanup. Finalizer CLI setsnice10. No live training module, policy hash or dispatcher changed. Existing main session42195 and committer29113 continue; no restart or extra full-data fitting. Native interval updated to30 minutes, preserving prompt/state. No deployment/API/database changes. Preserve unrelated upload/index edits and.DS_Store; no push.


## Actual verification and deliverables

- Initial focused fallback suite7 passed in1.75s. Full scoring-training suite **318 passed in10.57s** after report rendering/target-precedence checks; Ruff and whitespace passed. Final checkpoint-recovery additions verified with all8 focused fallback tests in1.61s, Ruff and `git diff --check` passed. Existing configured scoring/data coverage98.76% does not measure this new helper.
- Commands from`fastapi/`: standard full `pytest -c scoring_training/pyproject.toml scoring_training/tests`; focused `pytest .../test_campaign_fallback.py --no-cov`; `ruff check app/scoring scoring_training`. Tests exercise actual serialized prediction replay, partial-program/committer/target guards, duplicate decisions, regression/weak-model rejection, target-only backups, no-substantial outcome, resume after metadata failure, idempotence and retained hash/checkpoint restoration.
- Partial-program **preview only** on already completed original stages found186 substantial records and10 distinct selected decisions, first0036. No fallback finalizer, deletion or model activation was executed; this is not the final top-10 or a target achievement. Current main progress observed: mixed13/72 with0 failures, after robust90/90.
- New ignored`fallback-policy.json` records exact heuristic/hash/command. Native monitor will run the finalizer only after full research and original commits finish, visually inspect the regenerated figure and produce a NEW fallback execution report/local aggregate commit. Current main42195 and committer29113 remain unchanged; both pending training policies stay pinned.
- Implementation/monitor update task complete; actual post-run fallback execution and final selection remain pending with the full campaign. One local implementation/report commit, no push; unrelated upload/index work and.DS_Store excluded.
