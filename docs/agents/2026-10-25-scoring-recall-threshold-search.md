# Scoring threshold search with recall priority

## Request and constraints

- Find useful decision thresholds for the current credit scoring model, maximizing F1 while prioritizing detection of loans that will be written off (`LoanStatus=1`).
- Divide the work into small subtasks and make local commits in the existing `scoring_model` branch; do not push.
- Preserve unrelated work already present: the Hugging Face upload report/index change and an untracked model-directory `.DS_Store`.
- Keep the existing fitted model, calibrator, application contracts and deployed decision policy unchanged during this offline experiment.

## Subtasks and progress

1. Inspect package identity, cohort boundaries and baseline decision rules — complete.
2. Implement exact threshold enumeration and recall-aware selection with focused correctness tests — complete.
3. Add a reproducible offline experiment with frozen choices before later-cohort evaluation — complete.
4. Run the current model, compare F1/F2/recall and operational counts, document results and commit locally — complete.

## Findings and methodology

- Current package: `fastapi/models/sba-scoring-v1`, pinned by `fastapi/config/scoring-model.lock.json`; positive class is write-off=1.
- Final model was fitted on FY2010–2016. FY2017 (43,456 rows, 3,952 write-offs) trained its sigmoid calibrator; it can serve as a retrospective threshold-development cohort, but is not independent of calibration.
- Select thresholds on FY2017 only; save their values before reading FY2018–2019 (`test`) and FY2020–2026 (`transfer`). These cohorts were evaluated historically, so this is a new offline policy experiment on an existing benchmark, not a fresh external validation.
- F1 treats precision and recall equally. Compare maximum F1, maximum F2, and maximum F1 under recall floors 90%, 95%, 98%; a 95% floor is an explicit experimental assumption, not a supplied business constraint.
- Existing Java demo policy uses probability boundaries 0.15 and 0.35. A binary detection threshold is distinct from its multistep affordability/alternative-offer decision policy.

## Changes and deliverables

- `fastapi/scoring_training/thresholds.py`: exact score-boundary search with inclusive comparison, indivisible ties, confusion counts, precision/recall/F1/F2 and recall-constrained selection.
- `fastapi/scoring_training/tests/test_thresholds.py`: direct comparison to sklearn, tied scores/objectives, boundary decisions and invalid-input coverage.
- `fastapi/scoring_training/threshold_search.py`: pinned model/provenance verification, persisted development-only selection, fixed later-cohort/annual/backend-reachable evaluation, CSV and plot export.
- `fastapi/scoring_training/tests/test_threshold_search.py`: verifies that thresholds exist before holdout reads and remain fixed when holdout labels change; guards provenance and output overwrite.
- `fastapi/scoring_training/README.md`: CLI, assumptions and interpretation of outputs.
- `fastapi/experiments/sba-scoring-recall-thresholds-v1/`: Russian conclusions, immutable threshold selection, complete aggregated evaluation, comparison CSV, compact development grid, visually inspected figure and checksum provenance.
- `fastapi/experiments/README.md`: link to the scoring experiment.
- This report and a shared index entry.

## Experiment results

- Exact search: **41,892** attainable score-boundary candidates on FY2017. Full 7,235,370-byte curve remains in the ignored local run directory; its SHA-256 is recorded in the exported provenance. No loan-level records were added to Git.
- Maximum development F1: threshold **0.38752706815165333** (exact serialized value in `selection.json`), development F1 **0.732897**. Fixed test F1 **0.648614**, recall **0.767842**; transfer recall **0.461329**.
- Maximum development F2: threshold **0.164298163360983**, development F2 **0.802984**. Fixed test F1 **0.585503**, recall **0.859288**; transfer recall **0.555740**.
- Candidate under the explicit 95% development-recall assumption: threshold **0.054874051193982705**. Development recall **95.0152%**, F1 **0.600128**; test recall **92.2895%**, precision **28.4970%**, F1 **0.435475**; transfer recall **65.9668%**, precision **23.4634%**, F1 **0.346148**.
- On test this candidate detects **5,470/5,927** write-offs, misses **457**, and falsely flags **13,725** repaid loans. Relative to binary 0.35, it finds 809 extra write-offs, reduces missed write-offs by 63.90%, and adds 9,875 false flags.
- Development recall >=98% chooses **0.00896317675539934**; fixed test/transfer recall is **96.9968% / 81.5559%**, with F1 **0.303473 / 0.265327**.
- At the 95% development-recall candidate, backend-reachable test/transfer recall is **93.3566% / 41.6329%**. The temporal degradation is material; the development floor is not achieved on later cohorts.
- FY2026 contains 83 completed loans and no write-offs: recall is undefined, even though numeric exports use the documented `zero_division=0` convention.
- Outcome: useful offline candidates and explicit tradeoffs, **no demonstrated stable 95% future recall**. Further model/data work and a new untouched temporal cohort are planned recommendations, not completed work.

## Verification so far

- Read `AGENTS.md`, training/preparation documentation, split manifest, training/evaluation code, package loader and Java probability boundary references.
- `git status --short` confirmed the unrelated changes listed above.
- `git branch --show-current`: `scoring_model`; initial HEAD `d09b65b`.
- Training Python and Ruff are available in `fastapi/scoring_training/.venv/bin/`.
- Focused tests initially passed (20 cases); Ruff found one missing explicit `zip(strict=False)`, which was corrected. The final focused result is recorded below after rerunning.
- Final metrics-focused run: 21 tests passed; Ruff and `git diff --check` passed.
- Combined threshold/experiment-focused run: 26 tests passed; Ruff passed for all four new Python files.
- Full `scoring_training` suite: 222 tests passed in 14.90 seconds; configured existing scoring/data coverage 98.76% (95% gate passed). This coverage figure does not measure the new experiment modules; their correctness has dedicated tests.
- `scoring_training/.venv/bin/ruff check app/scoring scoring_training` and `git diff --check` passed.
- Actual experiment, from `fastapi/`: `scoring_training/.venv/bin/python -m scoring_training.threshold_search --prepared ../data/scoring/prepared/sba-v1 --package models/sba-scoring-v1 --output scoring_training/runs/sba-recall-thresholds-2026-10-25-v1 --recommended-recall 0.95` — exit 0; all three cohort outputs, CSVs and figure created.
- Matplotlib/fontconfig reported unwritable user cache paths inside the sandbox and successfully fell back to a temporary cache. Plot generation completed; the image was opened and visually inspected.
- Independent artifact verification: **24** exact comparisons of precision/recall/flagged count/flagged share at 0.15 and 0.35 across calibration/test/transfer match the frozen original package metrics.
- Verified SHA-256 of persisted threshold selection, both implementation modules, pinned manifest and every frozen model-package file; all matched.
- Markdown conclusions use the actual experiment counts and metrics; annual rows with no positives are explicitly explained.
- Exported file checksums, all fixed cohort thresholds and confusion-count invariants passed. `git diff --exit-code d09b65b -- fastapi/models/sba-scoring-v1 fastapi/config/scoring-model.lock.json fastapi/app backend/src/main` confirmed no task changes to package, model lock, API/runtime or backend implementation.

## Contract and migration impacts

None planned; offline outputs only. No API, database, model-package or runtime policy changes.

## Limitations

Historical SBA completed-loan data is a demo proxy. Mutable loan-term availability is unconfirmed; borrower overlap cannot be excluded; performance on these cohorts does not establish Russian banking PD or prospective production quality. Recall constraints on development data do not guarantee the same recall in later years.

## Git status and commits

- `efd3845` — record the experiment plan.
- `5004bf0` — exact recall-aware threshold metrics and 21 tests; shared index staged selectively to exclude the pre-existing upload entry.
- `0ede558` — frozen selection, temporal evaluation CLI and documentation, after the 222-test training-suite run.
- Final experiment artifacts and finalized report are saved in a separate local results commit accompanying this report.
- Git writes require sandbox escalation; the first unprivileged commit attempt failed to create `.git/index.lock`, and the authorized retry succeeded.
- Existing branch `scoring_model` retained. Unrelated upload-report/index work and `.DS_Store` remain outside task commits.
- No push performed.
