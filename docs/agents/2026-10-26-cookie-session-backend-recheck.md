# Recheck updated cookie-session backend

## Request and constraints
Recheck the team-updated cookie-session for backend/integration errors and repair confirmed defects. User additionally selected restoring the previously implemented customer/bank screens. Do not merge branches. Starting HEAD 1116793, tracking origin/cookie-session; working tree initially clean. No commit, branch switch or push requested/performed. Preserve team HF/local scoring support, cookie/CSRF and draft persistence.

## Confirmed defects and fixes
1. Journey returned the latest decision for the application without checking active_revision_id. After NEEDS_INFO, correction and resubmission it showed a stale decision. Added an active-revision filter. Regression first failed on original code, then passed after fix.
2. Reuploading a corrected document created a separate document while every previous failed version remained in the new submission. Added explicit optional replacesVersionId, app/type checks and latest-version conflict protection. It creates version N+1 under the same document; submissions freeze the latest version of each independent document. Old snapshots/files remain unchanged. Historical document reviews stay in audit but no longer change the requirement status for a superseding version.
3. The current branch lacked the previously added bank page/customer offer and demo-signing actions. Restored those source changes from the prior local implementation (5e2faeb), without merging any branch or replacing team ML code. Correct backend SIGNED and CREDIT_CONTRACT names are handled. Customer upload now offers explicit replace-versus-add selection with filename/version/review status; bank reviews only current versions.
4. Added protected GET /applications/{id}/documents metadata discovery, excluding storage_key. Ownership/bank access reuses existing guards. Restored bank queue, document review, macro context, guarded manual decision/scoring, saved-term display and demo disbursement.
5. Kept shared SELinux labeling on the scoring model-directory mount in disposable acceptance Compose.

## Contract and migration impact
- POST document multipart accepts optional replacesVersionId. Omitting it preserves separate-document uploads. Replacing another application's document gives 404; wrong type gives 400; stale version gives 409. Generated credit contracts cannot be uploaded/replaced by this endpoint.
- GET document list adds versionNo/current and latest review result, without filesystem paths.
- New submissions select one latest version per document; multiple independent documents of the same type are retained. Existing submitted revisions remain immutable.
- No database migration, model retraining, policy coefficient/threshold change or .env edit. Updated docs/backend-api.md for the additive contract.

## Commands and actual verification
- Initial `mvn -o -Dmaven.repo.local=/tmp/alpha-credit-m2 -f backend/pom.xml verify -q`: baseline suite passed.
- Added stale-decision regression: one test failed with old decision still present, establishing the bug before fix.
- Added document correction regression: failed before version replacement implementation; REQUEST_INFO persisted instead of APPROVED.
- Final `spotless:apply verify`: **72 Java tests, zero failures/errors**. Real disposable PostgreSQL, actual gateway HTTP fixtures. Coverage includes corrected-file resubmission, snapshot history, preserving independent attachments, superseded review isolation, stale-version conflict, wrong-type rejection and foreign-application rejection.
- Full current FastAPI offline suite in Docker: **564 passed, 7 intentionally skipped**, application branch coverage **97.76%**. Initial harness attempt could not write /app/.coverage on the read-only mount; rerun used COVERAGE_FILE=/tmp/cookie-recheck.coverage and passed.
- Ruff `app scripts tests`: passed. FastAPI/HF source and uv.lock remain unchanged from team HEAD.
- Frontend: **34 tests passed** (13 form/status, 10 session, 11 drafts); TypeScript/Vite and production Docker build passed. Status regression compares labels with actual backend workflow states.
- All three runtime images built from current source. First live acceptance attempt was started before frontend image export finished and failed to find that image; repeated after all builds completed and passed.
- Native four-outcome HTTP acceptance via nginx + separate owner/bank cookie/CSRF sessions, Java 21, real finetuned local E5, pinned HF CatBoost v2 and isolated PostgreSQL: APPROVED, COUNTEROFFERED, DECLINED, REQUEST_INFO passed; positive cases reached DISBURSED. Four stored model assessments, three linked decisions, only sba-scoring-v2. This is integration evidence, not model-quality validation.
- `scripts/check_cookie_https.py`: all six checks passed: certificate validation, untrusted certificate rejection, Secure/Host policy, no Secure cookie over HTTP, consecutive CSRF writes and logout cookie deletion.
- Main local Compose updated to verified images; nginx /api/health and loaded scoring identity checked. Database and document volumes preserved; no actual money movement.
- `git diff --check`: passed. Final branch remains cookie-session at 1116793; changes intentionally uncommitted, no branch merge/push.

## Actual browser checks
A separate ephemeral four-service fixture was created with synthetic accounts/data. Through the real UI:
- Owner cookie login and application restoration succeeded.
- Selected rejected fixture.pdf version 1 as replacement, uploaded corrected PDF, saw version 2 and awaiting-review state.
- Logged out and entered as demo bank; bank queue and role navigation restored.
- Bank saw only the current corrected file and confirmed it through the interface.
- Database verification: two retained versions, latest version 2. No real user data or financial operation used.
- Disposable fixture containers, DB/cache volumes and private credential file removed after verification.

## Evidence
- [Native four outcomes](artifacts/2026-10-26-cookie-backend-recheck/four-outcomes.json)
- [Browser replacement assertions](artifacts/2026-10-26-cookie-backend-recheck/browser-document-replacement.json)
- [Customer replacement screenshot](2026-10-26-cookie-document-replacement-proof.png)
- [Bank confirmation screenshot](2026-10-26-cookie-bank-replacement-proof.png)

## Sources / affected files
Current 1116793 sources and contracts, team merge/HF reports, application/document services, cabinet controller, Java integration tests; restored frontend App, Applications, Bank, UI, presentation/types/view and form regression from the prior implementation; disposable Compose SELinux mount; API contract documentation and this new report/index/evidence. Native ML modules/config/pins were preserved.

## Remaining limitations
No unresolved failure remains in the exercised backend/integration paths. This does not establish the absence of all defects. Scoring remains an SBA U.S. demonstration model with manually chosen risk/affordability/pricing rules and fixed demo currency conversion. Production credit quality/calibration, automatic macro-rate feed and real contract/payment integrations remain outside this test/fix scope. Live S3 and sustained production load were not verified; S3 fake-client regressions passed in the Python suite. Seven opt-in Python tests were skipped in the offline suite; real E5 and HF scoring were exercised separately by native HTTP acceptance. Documentation of the overall MVP remains a separate follow-up.
