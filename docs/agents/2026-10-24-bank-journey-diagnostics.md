# Bank login and submitted application diagnostics — 2026-10-24

Completed. Investigated the reported bank login loss and application stuck at
SUBMITTED. No application code, credentials or running-service settings changed.

## Findings

`frontend/src/App.tsx` keeps the Bearer token in React state, initialized empty.
Reload/new tab/full document navigation loses frontend authentication; internal
setPage navigation itself does not reset the token. Backend sessions in Accounts.java
last 12 hours and explicit logout revokes them. Frontend token loss does not itself
revoke the server session.

The frontend ignores bankApprover from `/me`. No frontend `/bank/*` calls or bank
queue/review screen exist. Submission saves a revision and sets SUBMITTED; it does
not automatically invoke bank processing. A BANK_APPROVER must call
`/bank/applications/{id}/process` or the allowed human decision endpoint.
Waiting on the customer screen therefore does not progress the application.

Bank queue, assignment, document/evidence reviews, processing, decisions and simulated
disbursement are implemented in backend. Offer acceptance and contract signing also
have API endpoints but no actions in the current frontend. The complete journey cannot
currently be performed through this UI. Real scoring integration is still pending;
the opt-in DEMO assessment and disbursement are synthetic.

## Verification and limitations

Inspected frontend App/Applications/api and backend Accounts/Security/ApplicationService/
CabinetController/RankingVocabulary plus existing integration tests. Applied the
api-testing skill and reused the existing regression tests.

`mvn -f backend/pom.xml -Dmaven.repo.local=/tmp/alpha-credit-m2 --batch-mode --no-transfer-progress -Dtest=BackendIntegrationTest test`:
exit 0; 24 tests, zero failures/errors/skips. Spring MockMvc with isolated Testcontainers
PostgreSQL and authenticated bank/customer roles. Covers submission, bank processing,
REQUEST_INFO/resubmission, counteroffers, explicit DEMO approval, acceptance, signing,
simulated disbursement and role isolation. This is API integration evidence, not a
completed browser flow or production-model verification.

Live login in the existing localhost browser failed with a connectivity message.
`docker compose ps` returned no running project containers. Did not restart services
or change credentials. The teammate's specific bank login and submitted application
were not reproduced; refresh token loss is confirmed by source inspection. Stopped
local containers are not evidence of an outage in the teammate's environment.

Branch backend-tasks_v2. Pre-existing working changes preserved; no commit or push.
