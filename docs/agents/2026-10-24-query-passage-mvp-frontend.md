# Query/Passage MVP, first frontend, universal task reports — 2026-10-24

Status: completed. Branch: `backend-tasks_v2`. Changes are local, uncommitted and unpushed.
This is a separate report for the current task; the completed October 23 report is preserved.

## Request and controlling constraints

- Adapt to the user's query_passage_mvp.md; preserve the attachment as requirements data.
- Begin a frontend based on the supplied Core Components documentation.
- The user personally transfers validated form results to the Recsys team and uploads their reply.
- Do not implement a model, training, embeddings, text generation, or a model HTTP client.
- Later user clarification specifies the exact Recsys reply: requestId, metadata, results;
  productId/productVersion/rank/similarityScore/isRecommended/eligibilityStatus/pendingConditions.
- Return all candidates, highlight first topK (maximum three), support empty results;
  similarity is cosine [-1,1], not approval probability or a percentage. No comments from Recsys.
- Final clarification extends the reporting workflow in AGENTS.md to every task, not just backend.

## Implemented behavior

### Form and Java checks

Preliminary Form 1.1 has 21 fields. Added request.usageMode (ONE_TIME/IN_PARTS/
ACCOUNT_RESERVE/UNKNOWN) and optional request.description (500 characters, no HTML).
Security readiness is YES/NO/DISCUSS/UNKNOWN instead of boolean. Missing/null remain unknown.
Required readiness maps YES to PASS, NO to FAIL, DISCUSS to REVIEW, UNKNOWN to UNKNOWN.
MSP membership remains boolean. Common purpose/sector/usage/readiness dictionaries are exposed.
The application schema remains 15 fields with 11 transferred fields; future application data
never enters queryFields. Existing financial/banking workflows and opt-in DEMO assessment remain
separate from Recsys. All eight backend demo scenarios now include usageMode and validate.

### Manual exchange

- GET /forms/preliminary/dictionaries
- GET /selection-profiles/{id}/recommendations/{runId}/ranking-export
- POST and GET /selection-profiles/{id}/recommendations/{runId}/ranking-result

requestId equals the immutable eligibility run UUID. Export freezes answers, semantic catalog,
product versions, checks and rankingTopK=3. INELIGIBLE products are excluded. Both ELIGIBLE and
CONDITIONAL candidates are passed. Semantic descriptions are authored only for the existing
15 synthetic products; they are not real Alfa Bank tariffs or invented model predictions.
The external team owns query/passage templates and the embedding implementation.

The response contains all candidates exactly once, ranks 1..N, scores descending in [-1,1],
and true flags exactly for ranks <= min(topK,3). Eligibility and pending conditions must echo
Java's values unchanged, including all fields and order. Tampering is rejected before insertion.
Scores retain Decimal precision; numeric strings, fractional ranks, boolean strings, unknown
fields/comments, duplicates and wrong IDs are rejected. metadata stores model/modelVersion/
queryTemplateVersion/passageTemplateVersion. Empty input accepts results: [].

Imports are immutable, one per run. Equivalent replay is idempotent; a different second reply
returns 409. Stale form versions (even after restoring original answers) and stale active catalog
versions cannot receive imports. Choosing a product alone does not stale the run. Historical GET
keeps original conditions and reports current=false after form edits. Company access is checked.
The result endpoint enriches results with original product/checks for rendering, without comments.

### Frontend

React 19, TypeScript, Vite. Uses actual official Button/Input/Textarea packages and CSS tokens
from Core Components (individual packages from release 50.38.0), not just imitation styling.
Reference: https://core-ds.github.io/core-components/master/?path=/docs/intro--docs
System font fallback is used; proprietary font binaries are not copied. Project icons/layout
are custom. UI explicitly labels the hackathon prototype and synthetic catalog.

Working flow: login -> company -> business/revenue -> need/readiness -> eligibility -> JSON
export -> manual handoff -> JSON upload/paste -> complete ordered result -> product choice.
First three recommended cards are highlighted, remaining cards stay visible. Scores are displayed
with four decimals and never multiplied by 100. Backend conditions remain visible on cards.
No textual model comments are displayed. A reply template is downloadable with score=null as an
unfilled placeholder, not a fake model score. Changes/empty/error/loading states are handled.
Form controls are disabled during writes; file inputs can accept a corrected file of the same name.

Bearer/password/form are not written to browser storage. After refresh, the downloaded request
file restores the server snapshot after authentication; local file conditions are not trusted.
Restoration also restores company and existing selection. Responsive CSS and keyboard modal focus
handling are included; actual mobile-device testing is still a separate follow-up.
The first UI covers preliminary selection; a full bank application UI is not implemented here.

### Reporting policy

AGENTS.md now requires a new uniquely named report under docs/agents/ for EVERY task, including
frontend, infrastructure, docs and research. docs/agents/log.md is the shared index. Historical
backend reports/index are preserved. This task's initially unfinished backend-area report was
moved to the shared directory; no completed report was modified.

## Files and migration impact

- Java: FormPolicy, Eligibility, SelectionProfiles, DemoScenarios; new RankingExchange,
  RankingNumbers, RankingVocabulary, ProductSemantics.
- V10__manual_ranking_results.sql: append-only credit.manual_ranking_result; SELECT/INSERT-only
  runtime grant, unique run reference. Converts legacy boolean readiness only in current profiles,
  increments their versions and clears old selection; historical snapshots are not rewritten.
- V1–V9 migrations were verified byte-identical to HEAD.
- frontend/: pinned npm lockfile, components, API helpers, typed exchange/form, styles, tests,
  Vite proxy, Dockerfile and nginx config. Compose adds frontend on localhost:3000; API proxy is /api.
- .env.example adds FRONTEND_PORT; the user's .env is unchanged. .gitignore excludes build info.
- docs/query_passage_mvp.md is byte-identical to the supplied attachment.
- docs/ranking-exchange.md and docs/contracts/ranking-response.schema.json document the final reply,
  strict validation, request matching, metadata and Postman scenarios.
- Existing API/data dictionary/storage/Postman/validation docs and README are updated.
- AGENTS.md, docs/agents/log.md, this report and the screenshot provide continuation context.

## Verification actually performed

1. `mvn -f backend/pom.xml -Dmaven.repo.local=/tmp/alpha-credit-m2 --batch-mode --no-transfer-progress verify javadoc:javadoc`
   passed: **35 tests**, 0 failures/errors/skips. Final completion: October 24, 14:34:08 Moscow.
   BackendIntegrationTest 17, DataPolicyTest 12, EligibilityTest 6. Real disposable PostgreSQL 17,
   runtime credit_app role, original SQL invariants. Spotless, jar packaging and JavaDoc/doclint pass.
   Host Java is 25 with release 21; Docker compilation/runtime use Java 21.
2. `npm --prefix frontend run build` passed TypeScript and Vite production build.
3. `npm --prefix frontend test` passed **3 tests**: false/zero/unknown serialization, IP->LLC field
   removal without mutation, synthetic example's complete 12-month past revenue interval.
4. Prettier check passed for frontend source/tests/config/lockfile/HTML and Compose. Contract schema
   was separately formatted and checked by Python jsonschema Draft 2020-12 with UUID format checks.
   Both the full browser fixture and empty results validate. Documentation links were checked.
5. `docker compose config --quiet` and `docker compose build frontend backend` passed, including
   a final rebuild after source changes. nginx image also served HTTP 200 in a disposable read-only
   container with tmpfs, cap_drop ALL and no-new-privileges. That smoke container was stopped.
6. Browser against a separate PostgreSQL and actual Spring server: login, synthetic form, checks,
   download event and actual request JSON file, file restoration, uploaded reply, successful import,
   product choice, reload and restoration of result/choice all succeeded.
   Six products remained, exactly three highlighted; scores 0.9000..0.6500 were not percentages;
   all original conditions remained. The reply was a clearly labeled BROWSER_TEST_FIXTURE_NOT_MODEL,
   prepared only for this test. It is not an implementation of Recsys and was not sent to anyone.
   Desktop 1280px: no horizontal overflow. Mobile CSS exists but no real-device QA was performed.
7. `git diff --check` passed. No production containers/volumes were restarted or migrated by testing.

Initial test attempts encountered sandbox Docker/socket and npm DNS restrictions; approved retries
were used. Intermediate contract/test mismatches were fixed before the final passing runs.
No failed intermediate result is reported as a successful final check.

## Preview / limitations / next team

The local preview is left available at http://127.0.0.1:5173 using the isolated Spring server
on 18080 and temporary Docker database alpha-query-passage-test-db on 15432. Only synthetic test
data is present. The development processes were started for this task; working project services
remain unchanged. The synthetic request downloaded by the browser is available in Downloads for
restoration on this test stand. Production startup remains documented in frontend/README.md.

No actual Recsys implementation was contacted or verified. The team should implement the documented
request/response exactly and supply real version metadata; backend does not vouch for a declared
model identity. Catalog semantics remain synthetic and must be agreed before real products.
A combined production Compose runtime and mobile devices were not tested; images built, nginx
static runtime worked, and browser API flow worked against the independent Java/Postgres stand.
There is no bank application UI yet. FastAPI remains its existing health-only placeholder.

Git: local changes on backend-tasks_v2; no commit, push, PR, or deployment performed.

[Frontend screenshot, synthetic result](assets/2026-10-24-frontend.png)
