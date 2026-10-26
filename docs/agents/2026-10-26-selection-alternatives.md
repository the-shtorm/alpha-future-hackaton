# Automatic alternatives for an empty product selection

## Request and constraints
Investigate the supplied equipment-financing example and offer concrete server-generated alternatives when no product matches. Preserve business facts and eligibility restrictions; require explicit customer acceptance of changed request terms. Work on cookie-session without merging branches or publishing changes. Existing manual-guidance report/index changes belong to the preceding task.

The user additionally requested verification of the complete login → preliminary form → recommendations/alternatives → application → scoring → subsequent workflow.

## Findings and changes
- Screenshot inputs: LLC, IT, USN, started 2024-01-01, MSP true, equipment 2000000 RUB / 12 months / one-time, revenue 2000000 RUB over April–June 2026, collateral NO, guarantor YES. The equipment product requires 1000000 RUB average monthly revenue and collateral; the supplied average is about 666667 RUB.
- Added SelectionAlternatives: at most three concrete alternatives only when no original product is ELIGIBLE/CONDITIONAL. It can decrease amount, clamp term and propose another usage mode. Equipment/vehicle/property purchases may be considered under an explicitly confirmed broader DEVELOPMENT purpose. It never raises the requested amount, substitutes unrelated purposes, changes company facts, invents income or assumes collateral/guarantors. Every proposal passes normal eligibility checks; short history remains conditional.
- Stored alternatives in immutable recommendation snapshots. Added explicit atomic acceptance using expectedVersion, saved server terms, fresh catalog checks and ordinary product selection. Old results become stale after acceptance. Failed/withdrawn choices roll back the complete transaction.
- Frontend displays proposed amount, term, purpose and usage, before/after changes, pending conditions and an explicit choice button. Accepted terms transfer into an ordinary application draft. Empty states no longer tell customers to guess different parameters when an alternative exists.
- Found premature ML calls in draft validation and before document/financial-evidence verification. Added policy preflight; draft validation/submission do not score. Missing/unreviewed documents or supplied financial evidence prevent model calls. Incomplete-document requests no longer misleadingly enter the SCORING stage.
- Updated the previously opt-in Java real-model test from obsolete v1 approval expectations to the actual v2/P07 approval fixture. Added an optional --selection-alternatives native acceptance path and separate scoring readiness check; benchmark output now follows --output instead of overwriting a historical repository artifact.

## Contract and migration impact
- Selection view adds alternatives[] with product, proposedRequest, answersPatch, changes and pendingConditions. Original results/rankingStatus remain unchanged; EMPTY describes original ranking candidates, not alternative availability.
- New POST /selection-profiles/{id}/recommendations/{runId}/alternatives/{productVersionId}/accept accepts expectedVersion and returns profile/selection. Client-supplied alternative answers are not accepted. Stale/replayed choices give 409; foreign/missing choices give 404. Existing ownership/CSRF guards remain active.
- POST /applications/{id}/validate is now preflight without external ML; SCORING_PENDING describes otherwise valid inputs awaiting bank processing.
- No DB migration, cookie/authentication change, model retraining, threshold change, Java–FastAPI contract change or model-source configuration change. FastAPI application modules, pins and .env were not edited.

## Actual verification
- Full Java `mvn -o -Dmaven.repo.local=/tmp/alpha-credit-m2 -f backend/pom.xml verify -q`, finally with RUN_REAL_SCORING_TESTS=1 and an isolated real scoring-v2 endpoint: **82 tests passed, zero failures/errors/skips**. Includes proposal generation, unchanged company facts, stale/foreign choices, transactional rollback, ordinary application creation, deferred scoring, document gates and real four-decision journeys. The first new rollback test used the runtime catalog role and failed on missing write permission; fixed the test fixture to use the existing test admin, without broadening runtime privileges.
- Frontend `npm test`: **34 tests passed**. TypeScript/Vite and final production Docker build passed. Both Java 21 and frontend Docker images built successfully.
- Python acceptance script compilation and Ruff check passed. Runtime image has no Ruff; used the existing scoring-integration-test image. System Python had no NumPy for the HTTP benchmark; reran using the bundled Python with NumPy.
- Actual browser on a disposable database: cookie login, all three form steps using screenshot inputs, automatic alternative rendering, explicit choice and opening the correct 2000000 RUB / 12 month P01 application draft succeeded. No main application test records were created.
- Native four-service nginx-cookie/CSRF → Java 21 → real finetuned E5 / native scoring-v2 → PostgreSQL 17 test passed for APPROVED, COUNTEROFFERED, DECLINED and REQUEST_INFO; the first two completed offer acceptance, demo contract and DISBURSED. Initial four-case audit: four model assessments, three linked decisions, only sba-scoring-v2.
- Additional real screenshot journey: P01 alternative, preserved business facts, no assessment during draft validation/submission or with missing documents, document review, corrected resubmission, cleared old decision and then one real model assessment. Final outcome **DECLINED**, reason NO_ACCEPTABLE_COUNTEROFFER, model probability about 0.252527. This is a successful integration with a negative credit-policy outcome, not an approval guarantee.
- HTTP regression benchmark: 50 single, 100 concurrent and 60 scoring requests mixed with real E5; ranking unchanged. Observed p95 about 12.7 ms single, 57.2 ms concurrent, 62.2 ms with E5. These are local measurements, not a production load qualification.
- `git diff --check`: passed.

## Local deployment and cleanup
Updated only main local backend/frontend to verified images; existing PostgreSQL/documents and FastAPI remained in place. Public /api/health returned status=ok; final frontend asset index-CCQ0eQ1S.js. Existing FastAPI model-info reports ready sba-scoring-v2. Disposable Compose services/volumes, additional opt-in ML container, private test configuration and the temporary copied model package were removed. No main DB seeding/uploads, branch changes, merge, commit or push.

## Evidence
- [Native pipeline including screenshot alternative](artifacts/2026-10-26-selection-alternatives/pipeline.json)
- [Real Java four-outcome test](artifacts/2026-10-26-selection-alternatives/java-native-four-outcomes.json)
- [HTTP benchmark](artifacts/2026-10-26-selection-alternatives/http-benchmark.json)
- [Browser alternative](2026-10-26-selection-alternatives-proof.png)

## Sources and affected files
Java SelectionAlternatives, SelectionProfiles, AutomaticSelection, ApplicationService and DataPolicy; SelectionAlternativesTest and BackendIntegrationTest; frontend App, Selections and types; scoring_stack_acceptance.py; docs/backend-api.md; this report, evidence and the shared index. Source material: supplied screenshots, current catalog policies/form schemas, prior backend recheck and native acceptance fixtures.

## Limitations and unresolved items
Fresh isolated HF-cache starts left scoring unavailable while recommendations were ready; the precise download/load failure was not isolated. The full passing runs used a read-only copy of the already pinned and validated native model package from the existing local HF cache. Thus successful scoring startup from an empty HF cache remains unverified in this environment; production HF configuration was not changed. Main local scoring was separately confirmed ready.

Scoring remains a demonstration model/policy; contract signing and disbursement are simulations. Recommendation/applicability is not credit approval, and some valid cases require bank review. No universally available alternative is promised when fixed business facts fail every catalog product. No unresolved failure remains in the exercised application/integration paths; this is not an exhaustive production certification.

## Git state
Branch cookie-session at f5c2a33, tracking origin/cookie-session. Changes intentionally uncommitted. The preceding manual-test-guidance report and its index entry are preserved separately. No merge, commit or push performed.
