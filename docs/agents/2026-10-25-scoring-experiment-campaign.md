# Executed scoring experiment campaign

## Request and constraints

- Execute the previously proposed retraining program, with an exact independent threshold search for each fitted candidate.
- Business target: recall >=90% and precision >=60%; report precision/F1/recall at the same operating point, never means over thresholds/folds.
- Preserve favorite `sba-scoring-v1`, threshold `0.15283707537791144`, original artifact hashes and recorded metrics. Keep runtime unchanged while experimenting.
- Small subtasks and local commits by completed stage, **not per combination**. No push. Preserve unrelated upload report/index work and `.DS_Store`.

## Progress

1. Audit original data, temporal feasibility and favorite preservation — complete.
2. Implement tested, restartable campaign runner and exact per-candidate reporting — complete.
3. Execute screening, refinement, robustness, warm-start, competitors and ensembles — complete.
4. Compare actual operating points, export aggregate artifacts and finalize local commits — complete.

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

- User changed the native monitoring interval to **10 minutes**. Verified the existing automation `automation` is ACTIVE with that saved interval using the automation view and its local TOML; no duplicate automation was created. Updated local monitor metadata and README to match. Quiet-on-unchanged notification policy and training CPU limits remain unchanged. These documentation updates join the next completed-stage commit; no extra polling commit or model checks were needed.

- Monitoring checkpoint 2026-10-25 22:47 Europe/Moscow: screening completed **480 records /384 distinct artifacts /0 failures** and automatically committed as `5ff1509`; refinement is running (36/360 records observed, no failures), both main/committer sessions remain alive. Newly announced fixed-threshold FY2023 maximum F1 and maximum recall with precision>=60%: `refine-0003`, t=0.09738818344101924, precision/F1/recall **0.662177/0.672365/0.682870**, TP1180/FP602/FN548. Compared with announced 0375, precision and F1 are higher while recall is lower by about 1.50 percentage points. Original9 term availability remains unconfirmed; joint 90/60 goal remains unmet. Identical 9,963/1,728 cohort and frozen selection hash verified; favorite and backup integrity pass, mixed policy remains enabled/frozen. No code changes, refits, threshold tuning, cleanup or duplicate process during monitoring.

- Monitoring checkpoint 2026-10-25 22:57 Europe/Moscow: refinement **57/360**, zero failures, both existing sessions live and log freshly updated. F1/precision>=60% leader remains announced `refine-0003`. New recall alternative `refine-0036` at frozen t=0.043127688704757465, common FY2023: precision/F1/recall **0.491920/0.585229/0.722222** (TP1248/FP1289/FN480). It improves all three metrics against the original favorite but trades markedly lower precision and F1 for higher recall than 0003; precision>=60% and joint 90/60 are unmet. Term remains unconfirmed. Verified identical 9,963/1,728 cohort, saved selection checksum and enabled/frozen mixed policy. Updated notification state; no code/training changes or cleanup.

- User approved another **100 distinct configurations ×2 shuffle strategies =200 additional fits**, after the previous72 and before final ranking/cleanup. Historical development FY2010–2019, outcomes known before2019-10-01; separate later-year FY2020–2026 and pooled fixed-threshold results. User authorized random whole-year resampling for sufficient classes (>=100 per class per role). Implementation/audits and294 passing tests are recorded in [top-100 extension report](2026-10-25-scoring-top100-recent-holdout.md). All later-year metrics remain adaptive historical checks because source parents were already selected using FY2023. Additional full-data fits are not yet run. Native monitor preserves10-minute interval and now guards completion on all200 attempts.

- Quiet monitoring checkpoint 2026-10-25 23:10 Europe/Moscow: refinement92/360, zero failures; primary and stage-committer sessions live, log updated2 seconds before inspection. Announced maximum F1 and overall recall unchanged; observed recall at precision>=60% increased by0.81 percentage points (`refine-0084`, P/F1/R0.627430/0.657670/0.690972 at t0.13445319122736146), below a material new notification milestone. Both72-fit and200-fit policies enabled with verified code hashes; no intervention, cleanup, restart, code/model changes or new commit.

- Monitoring checkpoint 2026-10-25 23:20 Europe/Moscow: refinement142/360, zero failures, both sessions live and log updated3 seconds before inspection. New announced FY2023 F1 leader `refine-0114`, frozen t=0.20164814049303642: precision/F1/recall **0.709900/0.681709/0.655671** (TP1133/FP463/FN595). Against previous F1 leader0003, P and F1 increase while recall decreases2.72 percentage points. Original9 term unconfirmed; joint90/60 target remains unmet. Same9,963/1,728 cohort, selection checksum and favorite/backup integrity verified; both extension policies enabled/frozen, concurrency unchanged. No fit/threshold changes, cleanup or duplicate processes during monitoring.

- User explicitly confirmed the exact rule via clarification: **Recall >=90% is the filter; among qualifying candidates maximize precision**. Precision60% is a target/flag, not eligibility. This supersedes both earlier rejected interpretations. Final top-10 and pending100-parent/historical shortlists now use that rule at already frozen thresholds; absent eligible candidates finalization/cleanup is forbidden. All metric deltas, dominance and tradeoffs against the unchanged favorite are explicit. Existing exploration/parents and four cache-hashed fit modules remain unchanged. See [recall-priority report](2026-10-25-scoring-recall-priority.md).

- Confirmed-objective implementation complete in `e80cafa` (supersedes rejected `a512bbd`): recall>=90% filter, maximize precision;297 tests passed in8.76s, Ruff/whitespace pass. Updated pending200-fit policy to the committed hashes before shortlist generation; retention/monitor match. Favorite/backup integrity verified; main/committer sessions live, refinement278/360 with0 failures. Current conditional leader0241 has P/F1/R0.246927/0.388160/0.906829 at t0.04497684248442092: higher recall but lower precision/F1 than favorite, explicitly a tradeoff, not dominance. Goal precision60% unmet.

- Quiet checkpoint 2026-10-25 23:42 Europe/Moscow: refinement285/360, zero failures; both sessions live, log updated3 seconds before inspection. Confirmed-objective leader0241 (recall>=90%, max precision) unchanged from the objective-correction checkpoint; precision60% still unmet. Both queued extensions and ranking hashes verified, control remains2×2/nice10. No model/threshold/code changes, restart, cleanup or extra commit; no actionable update to notify.

- Quiet checkpoint 2026-10-25 23:52 Europe/Moscow: refinement332/360, zero failures, main/committer sessions live, log age4 seconds. Recall90-filter/precision leader0241 unchanged, no joint90/60 achiever. Both extension policies and ranking code hashes verified; no intervention, code/model change, cleanup or extra commit.

- Monitoring checkpoint 2026-10-26 00:02 Europe/Moscow: refinement completed360/360,360 distinct artifacts, zero failures; stage commit `a7c8e04`. Competitor stage running31/168 without failures, both sessions live. Confirmed recall90/max-precision leader remains `refine-0241`, safe engineered features without term, t0.04497684248442092: P/F1/R0.246927/0.388160/0.906829. Against identical-cohort favorite, delta P/F1/R is **-24.40/-7.55/+46.76 percentage points**; a tradeoff, not dominance, precision60% unmet. Full cohort/selection checksum and original/backup integrity verified; no new fits/retuning/cleanup from monitoring, both queued extensions still enabled/frozen. Stage completion and conditional leader notified once.

- New user target **recall>=85% AND precision>=55% simultaneously**, ranked by precision among qualifying rows. Initial canonical primary/all-frozen-policy scan found0 hits on identical FY2023. Existing trained weights/thresholds remain unchanged; new mixed72/recent200 fits and composition selections use85/55 on historical threshold data before later-year evaluation. The100 parent sources use recall85/max-precision for retraining, not a claim that100 sources already meet55%. Empty-feasible outcome preserves all weights and has no substitute winner. See [85/55 extension report](2026-10-26-scoring-recall85-precision55.md);303 tests passed.

- User confirmed desired85%/55% with acceptable84%/53% and strong favorite improvement. Final eligibility requires both accepted bounds AND dominance over the favorite, with85/55 achievement separate. New-fit threshold target still85/55 before validation. Commits `e3d9249`/`e392157`,310 tests passed in10.43s; runtime policies and10-minute monitor synchronized. No accepted/goal points yet; full program continues. Final service committer session29113/PID from monitor is live at nice10; main session42195 unchanged. Original favorite/backup integrity and unchanged four fit/cache modules verified. See [current target report](2026-10-26-scoring-recall85-precision55.md).

- Quiet checkpoint 2026-10-26 00:19 Europe/Moscow: competitors40/168,0 failures; current long fits are500-tree random forests with unlimited depth, min_samples_leaf10 (two active trials), explaining a5-minute gap between completed records. Main42195/committer29113 remain live. No accepted84/53 or desired85/55 point among canonical primary or saved policy metrics. Both extension/target/ranking hashes and2×2 limit verified. No restart, load change, code/model mutation, cleanup or extra commit.

- Quiet checkpoint 2026-10-26 00:29 Europe/Moscow: competitors42/168,0 failures; previous long forests completed and next0042/0043 are running (unlimited depth, leaf10, max_features1). Main42195/committer29113 live, no qualifying84/53 or85/55 point among saved primary/alternative policies; frozen policies verified. No intervention/cleanup/code change or extra commit.

- Quiet checkpoint 2026-10-26 00:39 Europe/Moscow: competitors92/168,0 failures; random forests completed, current active0092/0093 areLightGBM, log freshly updated. Main42195/committer29113 live. No accepted84/53 or85/55 point among primary/other frozen policies; best favorite-dominating recall remains announced0036 (72.22%). Pending extension/target/ranking hashes verified. No intervention, extra fits/retuning/cleanup or commit.

- Monitoring checkpoint 2026-10-26 00:49 Europe/Moscow: competitors168/168 and warm24/24 complete without failures; their stage commit markers verified (warm `364e1fb`). Robustness now13/90,0 failures. Main42195/committer29113 live; favorite/backup integrity and pending extension hashes verified. No accepted84/53 or85/55 point yet; best dominating recall unchanged0036. Model seed42 remains the main selection seed; other robustness seeds are diagnostics, not picked as a lucky primary. Stage completion notified once; no monitoring-triggered refits, threshold changes, cleanup or duplicate processes.

- Quiet checkpoint 2026-10-26 00:59 Europe/Moscow: robustness20/90,0 failures; main42195/committer29113 live, log age71 seconds. Primary model-seed42 scan has no accepted84/53 or85/55 point and no new dominating-recall leader. Both queued extensions and target/ranking hashes verified. No intervention, refit/retuning/cleanup, load change or extra commit.

- Quiet checkpoint 2026-10-26 01:09 Europe/Moscow: robustness33/90,0 failures; main42195/committer29113 live, log age44 seconds. Seed42/FY2023 primary and alternative fixed-policy scans still0 acceptable84/53 and0 goal85/55, best dominating recall unchanged0036. Extension/target/ranking hashes verified; no intervention, retuning/cleanup/load change or extra commit.

- Quiet checkpoint 2026-10-26 01:19 Europe/Moscow: robustness42/90,0 failures; sessions42195/29113 live, log age26 seconds. Primary-seed42/FY2023 still0 acceptable84/53 or85/55 among frozen points; dominating-recall leader unchanged0036. Frozen policies verified; no intervention/cleanup/retuning/load change or commit.

- Quiet checkpoint 2026-10-26 01:29 Europe/Moscow: robustness58/90,0 failures; sessions42195/29113 live, log age30 seconds. Primary-seed42/FY2023 no acceptable84/53 or85/55 fixed-policy result; dominating-recall leader unchanged0036. Pending policy hashes verified; no intervention, retuning/cleanup/load change or extra commit.

- Quiet checkpoint 2026-10-26 01:39 Europe/Moscow: robustness75/90,0 failures; sessions42195/29113 live, log age43 seconds. No primary-seed42/FY2023 acceptable84/53 or85/55 frozen-policy point or new dominating-recall leader. Policies/hashes verified; no intervention, retuning/cleanup/load change or extra commit.

- Quiet checkpoint 2026-10-26 01:49 Europe/Moscow: robustness87/90,0 failures; sessions42195/29113 live, log age26 seconds. No primary-seed42/FY2023 accepted84/53/85/55 result or new dominating-recall leader; both queued policies and code hashes verified. No intervention, retuning/cleanup/load change or commit.

- User requested5-minute monitoring near the end of robustness. Existing native automation updated successfully and saved ACTIVE5-minute interval verified; local monitor metadata/README synchronized, no duplicate automation. Current robustness88/90 with0 failures; completion of this stage still leaves all72+200 mixed/refit attempts and compositions. No training resource change; documentation joins next stage/final commit.

- User restored30-minute monitoring and requested final substantial-improvement top-10 even if target candidates are absent. Added a separate POST-RUN fallback finalizer, so the live dispatcher and72/200 policies remain untouched. Operational substantial heuristic: recall+10p.p., F1+5p.p., no metric regression; rank recall/P/F1, deduplicate, no padding. It waits for the entire program and original commits, backs up target-only exports and replays before allowed retention. Full318 tests plus final8 focused checks passed. Partial-stage preview has10 distinct improvements, NOT final results. See [fallback implementation report](2026-10-26-scoring-fallback-top10.md).

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

### Completed stage: refinement

- 360 records; 360 distinct saved artifacts; 0 failed records. Exact per-point CSVs exported under `fastapi/experiments/sba-scoring-campaign-v1/stages/refinement`.
- Fold B, largest measured fixed-threshold validation F1: `refine-0114`, threshold 0.20164814049303642, precision **0.709900**, F1 **0.681709**, recall **0.655671**.

### Completed stage: competitors

- 168 records; 168 distinct saved artifacts; 0 failed records. Exact per-point CSVs exported under `fastapi/experiments/sba-scoring-campaign-v1/stages/competitors`.
- Fold B, largest measured fixed-threshold validation F1: `competitor-0033`, threshold 0.03997261747808091, precision **0.230007**, F1 **0.368572**, recall **0.927083**.

### Completed stage: warm

- 24 records; 24 distinct saved artifacts; 0 failed records. Exact per-point CSVs exported under `fastapi/experiments/sba-scoring-campaign-v1/stages/warm`.
- Fold B, largest measured fixed-threshold validation F1: `warm-0005`, threshold 0.037145512924654255, precision **0.503088**, F1 **0.587924**, recall **0.707176**.

### Completed stage: robustness

- 90 records; 90 distinct saved artifacts; 0 failed records. Exact per-point CSVs exported under `fastapi/experiments/sba-scoring-campaign-v1/stages/robustness`.
- Fold A, largest measured fixed-threshold validation F1: `robust-0066`, threshold 0.15328763852158048, precision **0.462220**, F1 **0.557161**, recall **0.701186**.
- Fold B, largest measured fixed-threshold validation F1: `robust-0022`, threshold 0.089549102489006674, precision **0.665505**, F1 **0.664348**, recall **0.663194**.
- Fold C, largest measured fixed-threshold validation F1: `robust-0047`, threshold 0.12920571633634872, precision **0.530466**, F1 **0.502547**, recall **0.477419**.

### Completed stage: postprocess

- 367 records; 367 distinct saved artifacts; 0 failed records. Exact per-point CSVs exported under `fastapi/experiments/sba-scoring-campaign-v1/stages/postprocess`.
- Fold A, largest measured fixed-threshold validation F1: `blend-2-0.1-A`, threshold 0.20269975839623453, precision **0.442084**, F1 **0.539173**, recall **0.690909**.
- Fold B, largest measured fixed-threshold validation F1: `mixed-v1-0002`, threshold 0.25125060103237185, precision **0.822206**, F1 **0.729556**, recall **0.655671**.
- Fold C, largest measured fixed-threshold validation F1: `blend-4-0.1-C`, threshold 0.17922870156809695, precision **0.562863**, F1 **0.511873**, recall **0.469355**.

## Final executed outcome

- 1489 measured records, 1288 distinct base-model artifacts, 0 failed records.
- No candidate meets both active constraints {'minRecall': 0.84, 'minPrecision': 0.53}; no fallback winner, no cleanup, all trial weights and favorite preserved.
- Final metrics refer to historical FY2023 validation; no fresh independent test or deployment is claimed.
