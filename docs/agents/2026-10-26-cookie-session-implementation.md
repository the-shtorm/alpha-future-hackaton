# Cookie sessions and reload restoration

## Request and constraints
Implement the selected HttpOnly cookie-session design and related authorization/reload
fixes. Create a branch from fast_api; the user explicitly requested the name
`cookie-session`, without a codex prefix. ML/scoring transfer belongs to the ML team
and is outside this change. Preserve existing Bearer integration clients and historical
reports; record actual results without credentials or personal data.

## Base and Git state
- Started from local fast_api at `114a50b`; current branch is `cookie-session` at that base.
  This base already includes one local commit beyond the previously fetched origin/fast_api.
- The auth-options-comparison report and its shared-index entry predated implementation;
  they are preserved and are not implementation changes.
- Implementation files remain uncommitted for review. No commit, push, merge, or PR was
  performed for this task. No rebase/merge was in progress.

## Implemented changes
- `backend/.../BrowserSessions.java`: cookie transport for existing opaque PostgreSQL
  sessions; host-only Path=/, HttpOnly, SameSite=Lax; Secure and __Host- names by default.
  Duplicate session cookies are rejected. Explicit Authorization always wins over cookies;
  invalid Authorization never falls back to a browser identity.
- `Accounts.java`: GET /auth/csrf and POST /auth/session. Browser login returns only
  status/expiresAt, issues a new identifier and revokes the previous cookie session in a
  transaction. Failed login preserves the existing session. Logout revokes the credential
  used for authentication and clears browser cookies when cookie-authenticated.
- `Security.java`: resolves cookie/Bearer identities from hashed, active, unexpired DB
  sessions; expired/revoked cookies are deleted. CSRF protects browser mutations,
  including login and multipart uploads. CSRF_INVALID is distinguishable from role denial.
  Repeated stateless authentication must not rotate CSRF on each request: rotation occurs
  only at actual browser login/logout. Request caching and built-in form logout are disabled.
- `application.yml`, `compose.yaml`, `.env.example`: explicit SESSION_COOKIE_SECURE policy.
  Java defaults to true; local HTTP Compose explicitly defaults to false.
- `frontend/src/api.ts`: same-origin cookie requests, CSRF bootstrap/cache and one retry
  only for CSRF rejection before controller execution; no automatic mutation replay for
  network errors or role denial. Multipart preserves the browser-generated boundary.
  Late responses from a previous session cannot repopulate private state. Public catalog
  responses remain usable when anonymous /me restoration or login changes session state.
- `App.tsx`, `view.ts`: /me startup restoration with visible loading/retry, 401 handling,
  login/logout broadcasts across tabs, synchronous duplicate-action guard. URL carries
  validated resource UUIDs and screen only, never credentials or form contents. Reload
  restores saved profile, recommendation result, saved list, or selected application.
- Preliminary answers autosave after 700 ms while signed in. Writes are serialized and
  reuse the server rowVersion. Conflict is surfaced without silently overwriting another
  tab. A saved profile is reused when submitting selection. Account/company/form changes
  invalidate pending saves. The notice distinguishes unsaved, saving, and saved states.
- `form.ts`: value comparison ignores JSON key order and normalizes money, so PostgreSQL
  jsonb key reordering does not trigger a redundant PATCH or reset a product selection.
- `Applications.tsx`: all existing read/write/upload operations use cookie/CSRF transport.
- Added backend cookie/CSRF tests and frontend API/view/session regression tests;
  package.json runs both frontend test files directly. Updated README and backend API docs.

## Contract, migration, deployment
- New browser endpoints described above; legacy POST /auth/login Bearer JSON contract
  remains available. Existing Bearer calls do not require CSRF. POST /auth/session always does.
- Existing api_session table is reused: SHA-256 identifiers, fixed absolute lifetime of
  12 hours and revocation. No DB migration, JWT, refresh-token store, HttpSession/JSESSIONID,
  sticky sessions, or ML-contract changes. Browser credentials are not stored in Web Storage.
- Frontend and /api must share one origin. For HTTPS deployment set
  SESSION_COOKIE_SECURE=true. Switching cookie mode requires signing in again.

## Commands and actual verification
- `mvn -f backend/pom.xml -Dmaven.repo.local=/tmp/alpha-credit-m2 --batch-mode
  --no-transfer-progress spotless:apply` — passed; formatting applied.
- `mvn -f backend/pom.xml -Dmaven.repo.local=/tmp/alpha-credit-m2 --batch-mode
  --no-transfer-progress verify` — BUILD SUCCESS: **57 tests, zero failures/errors/skips**,
  including 31 real-PostgreSQL integration cases and two cookie-policy unit tests;
  packaging and Spotless verification passed. Earlier new-test failures were repaired:
  role-test validation payload, document catalog code, mock cookie-attribute assertion,
  and the actual per-request CSRF reset. An attempted explicit-authentication strategy
  configuration was rejected by Spring for STATELESS and replaced with CSRF-specific
  authentication handling before the successful final run.
- `npm --prefix frontend test` — **22 tests passed** (12 form + 10 API/session/view).
  Covers cookie fetch options, shared CSRF bootstrap, CSRF retry bounds, no network replay,
  multipart, expiry notification, stale private response rejection, public-catalog race,
  URL validation and JSON-order-independent answer comparison.
- `npm --prefix frontend run build` — TypeScript and Vite production build passed.
- `git diff --check` — passed.
- `docker compose build backend frontend` — failed before build because Docker Hub registry
  was unreachable. Fallback built runtime images from already installed local image layers
  plus the verified JAR/dist; these image builds passed. Updated only backend/frontend using
  `docker compose up -d --no-build --no-deps backend frontend`; subsequent frontend fixes
  were rebuilt/restarted separately. PostgreSQL and FastAPI were not restarted or rebuilt.
- A live Python HTTP smoke through frontend /api verified no auth token in login JSON,
  actual HttpOnly/SameSite/Path/Max-Age headers on session cookie, HttpOnly/SameSite CSRF
  cookie, repeated cookie /me, rejection without CSRF, consecutive create/PATCH with the
  same CSRF, server-side logout/revocation. Synthetic selection reached real Java → FastAPI
  → Java with **rankingStatus READY and four candidates**, then loaded the same run again.
- Browser checks on localhost:3000: sign in; F5 retains login; edit and autosave preliminary
  amount/description/usage; F5 restores those exact saved values; selection returns four
  offers; F5 restores the result screen; choose product/create a draft; save a synthetic
  zero debt amount and F5 restores that draft/value; second tab restores the same login and
  saved list; logout in second tab clears private cabinet state and login in both tabs.
- Browser testing exposed and repaired the initial anonymous /me vs public-catalog race;
  a regression test now covers it. Final frontend build/test results above include the fix.
- Proof: [result screen after reload](assets/2026-10-26-cookie-session-results-reload.png).
  Local smoke data remains as two synthetic preliminary profiles and one unsubmitted draft.
  No real application was submitted, contract signed, or financial transaction performed.

## Remaining limitations and work
- Anonymous form state is memory-only. Signing in enables server draft persistence.
- Preliminary autosave has a debounce/network delay: wait for the saved notice before F5;
  invalid values and write conflicts are surfaced, not silently persisted. Reload starts the
  wizard at step 1 with the saved answers; the exact wizard step is not persisted.
- The final application form still uses its explicit Save draft button. Unsaved edits there
  are not restored on F5. Automatic saving of that separate form is future scope.
- Session renewal policy remains fixed 12 hours; no indefinite automatic renewal was added.
- Secure cookie attributes are unit-tested, but a real TLS/reverse-proxy deployment was not
  tested. Production deployment must enable Secure mode and be checked behind actual HTTPS.
- Full clean Docker image build remains unverified because the registry was unreachable;
  local runtime packaging and running-service checks passed as described above.
- Existing ML/scoring roadmap and broader backend MVP tasks were not re-audited or claimed
  complete by this authentication change. Current running recommendation path passed smoke;
  this does not establish scoring-model quality or production readiness.

## References
- Existing Accounts/Security/session SQL and frontend nginx same-origin proxy.
- Spring Security 6.5 CSRF documentation (consulted during implementation):
  https://www.springframework.org/spring-security/reference/6.5/servlet/exploits/csrf.html
- Previous architecture decision: 2026-10-26-auth-options-comparison.md.
