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
4. Run the current model, compare F1/F2/recall and operational counts, document results and commit locally — pending.

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
- This report and a shared index entry.

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

## Contract and migration impacts

None planned; offline outputs only. No API, database, model-package or runtime policy changes.

## Limitations

Historical SBA completed-loan data is a demo proxy. Mutable loan-term availability is unconfirmed; borrower overlap cannot be excluded; performance on these cohorts does not establish Russian banking PD or prospective production quality. Recall constraints on development data do not guarantee the same recall in later years.

## Git status and commits

- `efd3845` — record the experiment plan.
- `5004bf0` — exact recall-aware threshold metrics and 21 tests; shared index staged selectively to exclude the pre-existing upload entry.
- Git writes require sandbox escalation; the first unprivileged commit attempt failed to create `.git/index.lock`, and the authorized retry succeeded.
- No push performed.
