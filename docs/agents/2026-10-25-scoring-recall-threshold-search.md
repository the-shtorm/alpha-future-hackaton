# Scoring threshold search with recall priority

## Request and constraints

- Find useful decision thresholds for the current credit scoring model, maximizing F1 while prioritizing detection of loans that will be written off (`LoanStatus=1`).
- Divide the work into small subtasks and make local commits in the existing `scoring_model` branch; do not push.
- Preserve unrelated work already present: the Hugging Face upload report/index change and an untracked model-directory `.DS_Store`.
- Keep the existing fitted model, calibrator, application contracts and deployed decision policy unchanged during this offline experiment.

## Subtasks and progress

1. Inspect package identity, cohort boundaries and baseline decision rules — complete.
2. Implement exact threshold enumeration and recall-aware selection with focused correctness tests — pending.
3. Add a reproducible offline experiment with frozen choices before later-cohort evaluation — pending.
4. Run the current model, compare F1/F2/recall and operational counts, document results and commit locally — pending.

## Findings and methodology

- Current package: `fastapi/models/sba-scoring-v1`, pinned by `fastapi/config/scoring-model.lock.json`; positive class is write-off=1.
- Final model was fitted on FY2010–2016. FY2017 (43,456 rows, 3,952 write-offs) trained its sigmoid calibrator; it can serve as a retrospective threshold-development cohort, but is not independent of calibration.
- Select thresholds on FY2017 only; save their values before reading FY2018–2019 (`test`) and FY2020–2026 (`transfer`). These cohorts were evaluated historically, so this is a new offline policy experiment on an existing benchmark, not a fresh external validation.
- F1 treats precision and recall equally. Compare maximum F1, maximum F2, and maximum F1 under recall floors 90%, 95%, 98%; a 95% floor is an explicit experimental assumption, not a supplied business constraint.
- Existing Java demo policy uses probability boundaries 0.15 and 0.35. A binary detection threshold is distinct from its multistep affordability/alternative-offer decision policy.

## Changes and deliverables

- This report; shared index entry will be added with the implementation.

## Verification so far

- Read `AGENTS.md`, training/preparation documentation, split manifest, training/evaluation code, package loader and Java probability boundary references.
- `git status --short` confirmed the unrelated changes listed above.
- `git branch --show-current`: `scoring_model`; initial HEAD `d09b65b`.
- Training Python and Ruff are available in `fastapi/scoring_training/.venv/bin/`.
- No experiment or tests have been run yet.

## Contract and migration impacts

None planned; offline outputs only. No API, database, model-package or runtime policy changes.

## Limitations

Historical SBA completed-loan data is a demo proxy. Mutable loan-term availability is unconfirmed; borrower overlap cannot be excluded; performance on these cohorts does not establish Russian banking PD or prospective production quality. Recall constraints on development data do not guarantee the same recall in later years.

## Git status and commits

In progress. No commits or push performed by this task yet.
