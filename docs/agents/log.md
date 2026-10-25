# Task reports

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
