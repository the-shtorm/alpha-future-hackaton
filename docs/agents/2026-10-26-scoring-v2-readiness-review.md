# sba-scoring-v2 readiness clarification

## Request and sources

User asked whether the selected primary model is completely ready to use. Read the primary scoring lock, native package evaluation, and completed promotion report. This is a separate read-only readiness review; no runtime/model/policy changes or new training.

## Verified status

The primary lock selects sba-scoring-v2. Loaded the native package again with its pinned manifest SHA and evaluated a synthetic request through ScoringPackage; identity, probability/score and frozen threshold were verified. All package integrity/dependency checks passed. Prior promotion verification recorded320 scoring-training tests (98.77% configured scoring/data coverage),16 API tests and exact9963-row historical FY2023 native replay. These tests were not rerun during this review.

Docker now responds, but `docker ps --format '{{.Names}} {{.Status}}'` returns no running containers. Initial sandbox permission error was resolved by running the same read-only command with approval. No running application stack was verified or started. Prior statement that Docker daemon was unavailable applied to the promotion session; current finding is an available Docker daemon with no running containers.

## Conclusion and limits

Ready as a packaged, calibrated demo inference model and configured primary. A complete running-stack deployment/acceptance remains unverified. It is not validated for real banking decisions: FY2023 is previously inspected historical validation, desired85/55 is unmet, term historical availability is unconfirmed, and later completed-loan cohorts show deterioration. At frozen t=0.167204479067272: FY2023 precision58.96%/F1 64.04%/recall70.08%; FY2024 37.25%/43.27%/51.61%; FY2025 3.43%/5.08%/9.76%. No new independent test or production suitability claim.

No schema, contract or migration changes. Report/index only, local commit without push. Unrelated Hugging Face report/index insertion and v1 .DS_Store remain excluded.
