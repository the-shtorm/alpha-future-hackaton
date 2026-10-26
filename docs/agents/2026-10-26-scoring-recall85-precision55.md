# Search for recall85% and precision55% jointly

## Request and scope

User set **recall>=85% AND precision>=55%** as the desired target, then explicitly allowed borderline84%/53% while emphasizing strong favorite improvement with a recall focus. Keep the clarified maximum-precision ordering among qualifying variants, with recall/F1 for ties. Improve preserved favorite on identical FY2023 cohort; report all three metrics at one frozen threshold. Continue the entire original program,72 mixed fits and200 top-100 refits,2 active fits ×2 threads, nice10, no push or per-combination commits.

## Actual initial search

Read every canonical completed foldB result: **zero** jointly eligible primary points and **zero** other previously frozen policy points on FY2023. No validation threshold scan or retuning. Earlier inspected later-year cohorts remain historical validation, not a new independent test.

## Implemented changes

- Shared active target85/55, jointly eligible final top-10 and no substitute under either constraint. Existing raw fit records and their historical90/60 flags remain untouched; current eligibility is calculated explicitly.
- Added `campaign_target.py` for NEW late-stage fits/compositions: exact development threshold enumeration at85/55, choose maximum precision subject to recall85%, freeze before validation. Worker-local adapters restore prior functions. Four core training/cache-hashed files unchanged.
- Mixed72 and recent200 configurations include target-code hashes; their policies/protocol hashes are advanced BEFORE their first full-data fit. Class-sufficiency splits/cutoffs/source data unchanged.
- The100-source shortlist uses recall>=85%, then precision, even if sources have not yet reached55% precision; these are starting configurations for retraining, not claimed successful variants. Requiring all100 sources to meet the new goal now would be impossible and silently cancel the authorized200 fits. Final/historical finalist lists require BOTH85/55.
- If all planned attempts finish without a feasible candidate, export empty top-10, honest completed-no-feasible summary and all diagnostics, preserve ALL trial weights and favorite; no replay/deletion is claimed. Update/restart only the service that commits completed stages so its final report supports that outcome; main training remains running.

## Verification and Git

Tests, runtime policy synchronization, process evidence and final local commits recorded below. No API/database/active model change. Preserve unrelated upload report/index work and .DS_Store.


## Verification checkpoint

- Read all completed canonical foldB records and all four saved validation policy points:0 joint85/55 hits at task start. No model quality inferred from fixture tests.
- Focused fit/export suite37 passed in4.83s. Full scoring-training suite **303 passed in10.32s**; an import-order lint issue was then fixed and lint/whitespace rechecked separately. Coverage98.76% applies to configured existing scoring/data modules, not new campaign modules.
- Tests include actual mixed/recent fits asserting development85/55 constraints and best-precision-at-recall primary policy; reversed-validation-label independence; spawned workers; both success and no-feasible final exports; all weights retained in no-feasible path; final report never claims replay/cleanup in that path.
- Command from `fastapi/`: `MPLCONFIGDIR=/tmp/alpha-scoring-mpl OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 scoring_training/.venv/bin/python -m pytest -c scoring_training/pyproject.toml scoring_training/tests`. `ruff check app/scoring scoring_training` and `git diff --check` recorded after style fix below.
- Runtime policy/monitor synchronization and committer restart follow the implementation commit; no full-data72/200-stage fit has run yet.


## User steering incorporated before finalization

User explicitly allowed borderline84% recall/53% precision, retained85%/55% as the desired target, and emphasized **strong improvement of the preserved favorite with a recall focus**. Final eligibility now requires84/53 AND dominance over the original favorite in precision/recall/F1 on identical FY2023 rows (at least one strict gain). Full85/55 achievement and borderline acceptance are separate flags. Higher precision among eligible variants remains the previously clarified ranking; recall/F1 break ties. Source100 uses recall84% for retraining starts. New-fit development threshold selection still aims85/55 before later-year scoring. No lower-quality padding or automatic model replacement.


## Final implementation/queueing result

- Final suite after tolerance/dominance changes: **310 passed in10.43s**; Ruff and `git diff --check` passed. Boundary cases84%/53%, below-bound rejection, separate85%/55% flags, and a tolerable-but-worse-than-favorite candidate are covered. No padding with non-improvements.
- Final primary/all-frozen-policy scan still found0 accepted84/53 rows and0 desired85/55 rows at this checkpoint.100 distinct source configurations remain available under recall84% for the approved200 refits. These are source starts, not successful target models.
- Implementation commits `e3d9249` (85/55 and no-feasible outcome), `e392157` (84/53 tolerance plus favorite dominance). Both pending72/200 policies atomically advanced to the committed splitter/target/ranking hashes before ANY full-data fit in those branches. Retention/monitor metadata and10-minute automation synchronized. New-fit development threshold target remains85/55.
- Original favorite and backup passed actual `ScoringPackage` integrity checks after final policy synchronization. Confirmed zero changes to the four core cache-hashed training modules sincebc9638a.
- Only the completed-stage committer was restarted to load final target/export/report code; old PID verified by command and stopped before replacement. Final session29113 is running with verified nice10; monitor stores the new PID/session. Main training session42195 was never restarted and remains live,2×2 limit unchanged. Current competitor checkpoint40/168, zero failures.
- Implementation/configuration task complete; full research program and final measured top-10 remain in progress under the parent campaign. No cleanup/model activation during this task. New report/index committed separately; unrelated upload/index work and.DS_Store preserved; no push.
