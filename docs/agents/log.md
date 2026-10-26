# Task reports

- [2026-10-26 — Merge cookie-session into pre-docs and verify](2026-10-26-merge-cookie-session-into-pre-docs-and-verify.md) — completed; clean merge of 1116793, 70 Java/564 FastAPI/33 frontend tests plus real E5/SBA tests, HTTPS and four actual cookie-auth credit outcomes passed; local merge, no push; UI and main .env limits recorded.

- [2026-10-26 — Credit pipeline state audit](2026-10-26-credit-pipeline-state-audit.md) — completed; backend demo workflow confirmed by 57 tests, 33 frontend tests/build passed; missing bank/post-decision UI and local Compose configuration blockers documented; original verify blocked by CRLF/Spotless.

- [2026-10-26 — GitHub push DNS diagnosis](2026-10-26-github-push-dns-diagnosis.md) — completed; current DNS resolution and SSH read access passed, retry original push; no configuration changes or push.

- [2026-10-26 — Complete draft persistence and HTTPS checks](2026-10-26-complete-draft-persistence-and-https-checks.md) — completed on cookie-session; guest transfer and final autosave/F5/conflict checks, 33 frontend tests, full Java/frontend Docker builds and real TLS/Secure-cookie acceptance passed; uncommitted.

- [2026-10-26 — Cookie session implementation](2026-10-26-cookie-session-implementation.md) — completed on cookie-session; HttpOnly/CSRF, reload and draft restoration; 57 Java + 22 frontend tests and live browser/Java→FastAPI checks passed; uncommitted for review.

- [2026-10-26 — Auth architecture comparison](2026-10-26-auth-options-comparison.md) — completed; compared browser Bearer persistence with HttpOnly server sessions, scaling and renewal; sources checked, no implementation.

- [2026-10-25 — Finish git pull rebase](2026-10-25-finish-fast-api-pull-rebase.md) — restored the verified resolution after pull rebased the integration commit; application tree unchanged from the tested merge, no push.

- [2026-10-25 — Resolve merge with origin/fast_api](2026-10-25-merge-origin-fast-api.md) — completed; both conflicts resolved preserving model-source and SELinux support; 201 FastAPI tests, 11 frontend tests/build, real CPU model and Java/draft acceptance passed; local merge, no push.

- [2026-10-25 — Commit Java/FastAPI integration work](2026-10-25-commit-fast-api-integration.md) — completed; integration fixes and verification artifacts included in the user-requested local commit; staged diff check passed, no push.

- [2026-10-25 — fast_api integration verification and repairs](2026-10-25-fast-api-integration-check.md) — completed; SELinux/model/startup repaired; 52 backend, 169 FastAPI, 11 frontend tests and real E5/form/product/draft acceptance passed; remaining limitations recorded.

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
- [2026-10-25 — Полный лог FastAPI, RecSys и дообученной E5](2026-10-25-fastapi-recsys-full-work-log.md) — сервер v2, Java-интеграция, калибровка/reranker/дообучение, текущая F1-политика, HF/local/S3, Docker, проверки и ограничения; строгая приёмка всего сервера на 6 ГБ и экспертная оценка качества остаются незавершёнными.
- [2026-10-26 — cookie-session: FastAPI/Java/frontend compatibility review](2026-10-26-cookie-session-recsys-review.md) — 203 FastAPI tests, 33 frontend tests and real cookie/CSRF/Java/E5 flows passed; inherited CI defect recorded.
- [2026-10-26 — cookie-session: CI model-path correction and report commit](2026-10-26-cookie-session-ci-model-path-fix.md) — removed test-only path overrides, preserved runtime MODEL_PATH, archived review evidence.
- [2026-10-25 — Credit scoring implementation](2026-10-25-credit-scoring-implementation.md) — preparatory phase completed; shared contract/features and temporal preparation, 163 tests passed; continued in the training/integration report below.
- [2026-10-25 — SBA training and integration](2026-10-25-credit-scoring-training-integration.md) — completed; trained/calibrated CatBoost, FastAPI/Java policy/audit, four real HTTP journeys; 380 Python tests plus real E5 regression, 66 Java tests; local commits only.
- [2026-10-25 — Scoring recall threshold search](2026-10-25-scoring-recall-threshold-search.md) — completed; 41,892 thresholds, 222 tests; fixed later-cohort evaluation exposes recall degradation; local commits only, runtime policy unchanged.
- [2026-10-25 — Retraining strategy for recall 90% and precision 60%](2026-10-25-scoring-retraining-precision-recall-plan.md) — completed proposal; 480 primary combinations, up to 1,122 planned fits; tested joint-constraint selector, 241 tests; new training not run, local commits only.
- [2026-10-25 — Favorite scoring threshold: test clarification](2026-10-25-favorite-scoring-threshold-test-clarification.md) — completed; favorite p>=0.152837 recorded; clarified calibration vs fixed test/transfer metrics; no new experiments.
- [2026-10-25 — Scoring experiment campaign](2026-10-25-scoring-experiment-campaign.md) — completed; full campaign, no jointly feasible candidate, all weights/favorite preserved; local commits only.
- [2026-10-25 — Random-row and random-year scoring extension](2026-10-25-scoring-mixed-split-extension.md) — implemented and audited; 72 additional fits queued for the ongoing campaign, fixed FY2023 comparison; 281 tests passed.
- [2026-10-25 — Top-100 shuffled-history scoring extension](2026-10-25-scoring-top100-recent-holdout.md) — implemented/audited; 200 additional fits queued, FY2020–2026 fixed evaluation, sufficient-class splits; 294 tests passed.
- [2026-10-25 — Confirmed recall90 filter and precision optimization](2026-10-25-scoring-recall-priority.md) — completed; recall>=90% eligibility then maximum precision, explicit favorite tradeoffs, queued policy synchronized;297 tests passed.
- [2026-10-26 — Scoring target85/55 with84/53 tolerance](2026-10-26-scoring-recall85-precision55.md) — implemented/queued; require favorite improvement,310 tests, safe no-feasible outcome; full campaign continues.
- [2026-10-26 — Final fallback top-10 improvements](2026-10-26-scoring-fallback-top10.md) — implementation complete; post-run replay/retention pending,30-minute monitor,318 full-suite tests plus8 focused checks; main training unchanged.
- [2026-10-26 — Verified scoring fallback execution](2026-10-26-scoring-fallback-execution.md) — completed; full1489 records,0 failures; target unmet,10 verified substantial improvements retained; favorite preserved, local commits only.
- [2026-10-26 — Selected scoring model5](2026-10-26-scoring-selected-model-0051.md) — completed; mixed-v1-0051 preserved separately, copied model replay/checksums verified; runtime unchanged, local commit only.
- [2026-10-26 — Primary sba-scoring-v2 promotion](2026-10-26-scoring-v2-primary.md) — completed; native export/replay, primary pin/defaults,320 scoring-training and16 API checks; v1 preserved, Docker deployment not run.
- [2026-10-26 — sba-scoring-v2 readiness review](2026-10-26-scoring-v2-readiness-review.md) — completed; native demo inference verified again, no running containers; deployment and real banking validity not established.
- [2026-10-26 — Model directory cleanup](2026-10-26-scoring-model-directory-cleanup.md) — completed; only E5/SBA v1/v2 remain, redundant copy removed; source export/replay and package hashes verified.
- [2026-10-26 — Scoring HF / local source](2026-10-26-scoring-hf-parameterized-source.md) — implemented on scoring_model; pinned public HF, offline cache/RAM verified, 536 Linux tests passed, Java source-smoke passed; legacy v1 approval fixtures need updating; no commit/push.
- [2026-10-26 — Scoring v2 approval fixture](2026-10-26-scoring-v2-journey-fixture-update.md) — completed; P07 approval fixture, all four real HTTP outcomes passed, approved/counteroffered disbursed; model/threshold/Java policy preserved, no commit/push.
- [2026-10-26 — Commit scoring HF migration](2026-10-26-commit-scoring-hf-migration.md) — local commit of HF/local loading, scoring package cleanup, documentation/artifacts and v2 HTTP fixtures on scoring_model; no push.
- [2026-10-26 — Merge scoring into cookie-session](2026-10-26-merge-scoring-into-cookie-session.md) — local merge and compatibility verification; preserves cookie/CSRF, E5 local/HF/S3 and native scoring HF/local.

- [2026-10-26 — Updated cookie-session backend recheck](2026-10-26-cookie-session-backend-recheck.md) — completed; stale decisions and replacement documents fixed, customer/bank screens restored without merge, 72 Java/564 Python/34 frontend tests, native HF/cookie journeys and HTTPS/browser checks passed; uncommitted.
