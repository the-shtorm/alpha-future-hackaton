# Task reports

Each task has its own report. Reports cover every area of work and are never combined
or overwritten. Historical backend reports remain available in their original location.

- [2026-10-23 — Data Policy 2.1 and Preliminary Form 1.0](backend/2026-10-23-data-policy-2-1.md) — completed.
- [2026-10-24 — Query/Passage MVP, frontend and universal task reports](2026-10-24-query-passage-mvp-frontend.md) — completed; 35 backend tests, 3 frontend tests, both Docker images built.
- [2026-10-24 — Customer frontend and automatic selection](2026-10-24-customer-frontend-automatic-selection.md) — paused by user at that stage; customer UI continued in the catalog-and-demo-login report below.
- [2026-10-24 — Backend fields aligned with corrected policy/form](2026-10-24-backend-fields-v3.md) — completed; 44 backend tests, style, build and JavaDoc passed.
- [2026-10-24 — Frontend Docker Compose build fix](2026-10-24-frontend-compose-build-fix.md) — completed; Compose build/start passed, 6 frontend and 45 backend tests passed.
- [2026-10-24 — Demo account check](2026-10-24-demo-account-check.md) — completed; optional demo account is not configured/created in running Compose.
- [2026-10-24 — Catalog and demo login](2026-10-24-catalog-and-demo-login.md) — completed; demo login and public catalog verified in Docker/browser, 7 frontend tests passed.
- [2026-10-24 — Form controls, alignment and validation](2026-10-24-form-controls-and-validation.md) — completed; 48 backend and 11 frontend tests passed, Docker rebuilt, form/application controls and low-revenue empty result verified in browser.
- [2026-10-24 — Interface animations](2026-10-24-interface-animations.md) — completed; frontend build and 11 tests passed, Docker rebuilt, dialogs/dropdowns/step transitions verified in browser.
- [2026-10-24 — Scoring readiness check](2026-10-24-scoring-readiness-check.md) — completed; source inspection confirms real scoring integration is still pending.
- [2026-10-24 — Bank journey diagnostics](2026-10-24-bank-journey-diagnostics.md) — completed; 24 backend integration tests passed; bank UI absent and refresh loses frontend token; live login blocked by stopped local containers.
- [2026-10-25 — Credit scoring implementation plan: Markdown export](2026-10-25-credit-scoring-plan-export.md) — completed; full agreed plan saved, Markdown structure and local links verified; no training or application changes.
- [2026-10-25 — Credit scoring implementation](2026-10-25-credit-scoring-implementation.md) — preparatory phase completed; shared contract/features and temporal preparation, 163 tests passed; continued in the training/integration report below.
- [2026-10-25 — SBA training and integration](2026-10-25-credit-scoring-training-integration.md) — completed; trained/calibrated CatBoost, FastAPI/Java policy/audit, four real HTTP journeys; 380 Python tests plus real E5 regression, 66 Java tests; local commits only.
- [2026-10-25 — Scoring recall threshold search](2026-10-25-scoring-recall-threshold-search.md) — completed; 41,892 thresholds, 222 tests; fixed later-cohort evaluation exposes recall degradation; local commits only, runtime policy unchanged.
- [2026-10-25 — Retraining strategy for recall 90% and precision 60%](2026-10-25-scoring-retraining-precision-recall-plan.md) — completed proposal; 480 primary combinations, up to 1,122 planned fits; tested joint-constraint selector, 241 tests; new training not run, local commits only.
- [2026-10-25 — Favorite scoring threshold: test clarification](2026-10-25-favorite-scoring-threshold-test-clarification.md) — completed; favorite p>=0.152837 recorded; clarified calibration vs fixed test/transfer metrics; no new experiments.
- [2026-10-25 — Scoring experiment campaign](2026-10-25-scoring-experiment-campaign.md) — in progress; favorite backed up and verified, versioned point-in-time protocol, per-candidate exact thresholds, stage-level local commits.
