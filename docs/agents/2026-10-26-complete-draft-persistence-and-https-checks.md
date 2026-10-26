# Complete draft persistence and HTTPS checks

## Request and scope
The user highlighted the previous limitations (anonymous form loss, manual final-draft
saving, missing HTTPS verification and incomplete full image build) and asked why they
were left unfinished. Complete their local implementation and verification on the
existing `cookie-session` branch. Preserve previous uncommitted work and completed
reports. Do not publish externally, install a global test CA or expose credentials.

## Initial and final Git state
- Branch: cookie-session, based on local fast_api 114a50b. Previous cookie-session work,
  auth-comparison report and index entry were already uncommitted; they are preserved.
- This task adds to that working tree. No commit, push, merge, PR or remote deployment.
- Historical cookie-session report records the earlier state and remains unchanged;
  the limitations closed here are superseded by this report and current README/API docs.

## Changes and affected files
- `frontend/src/drafts.ts`: bounded, versioned, 24-hour preliminary guest draft in
  sessionStorage, restricted to the existing 15 preliminary fields. No auth credentials,
  account IDs or final-application fields are persisted. Invalid/expired/corrupt stored
  data is rejected; unavailable browser storage is handled without a crash or false
  saved claim. Data is scoped to the tab and removed after server transfer or logout.
- `App.tsx`: restores the guest draft after anonymous /me on F5, preserves it on a
  login broadcast, transfers it to the authenticated server profile and removes the
  temporary copy only after successful persistence. Preliminary forms flush before
  internal navigation; authenticated unsaved preliminary edits have a beforeunload guard.
- `DraftWriter` serializes final-application PATCH writes, captures each input snapshot,
  advances expectedVersion using actual responses, skips equivalent writes and blocks
  after 409 rather than overwriting another tab. Disposal rejects queued/late results.
- `Applications.tsx`: debounced 700 ms autosave for DRAFT/NEEDS_INFO, visible saved/dirty/error
  state, no replacement of newer typing by older save responses, conflict recovery via
  Load current version. Explicit saving remains available. Back/header navigation,
  status refresh and document upload wait for a save; navigation disables editing while
  awaiting it. Dirty final forms also have a beforeunload guard. Confirmation resets
  when answers change; autosave never submits an application.
- Manual submit waits for queued saves. A submit with unknown outcome retains its
  original idempotency key/version and freezes edits/autosave until explicit verification;
  confirmation is still required for the initial submission. This avoids autosave
  interfering with a possibly committed submit. This UI network-failure path was reviewed,
  but not fault-injected in the live browser; writer timeout/locking behavior is tested.
- `frontend/tests/drafts.test.mjs`, `package.json`: guest persistence and concurrency tests.
- `compose.session-test.yaml`, `infra/session-test/nginx.conf`,
  `scripts/check_cookie_https.py`: disposable real TLS reverse-proxy acceptance with
  separate PostgreSQL, SESSION_COOKIE_SECURE=true, random loopback ports and random
  test-only passwords. OpenSSL creates a short-lived CA/server certificate with correct
  SAN/key-usage constraints. Python validates CA and hostname; no verification bypass.
  The CA is trusted only by that client context and is not installed system-wide.
- README and backend-api docs now describe both autosaves, guest lifetime, conflict and
  navigation behavior, HTTPS test invocation and its actual local scope.
- New report/shared-index entry and test artifacts listed below.

## Contract and migration impacts
No Java endpoint, database schema or ML contract changes in this follow-up. Autosave uses
existing POST/PATCH APIs and optimistic versions. Manual submission remains a separate,
explicit operation. Cookie credentials remain HttpOnly and never enter Web Storage.
The main local application keeps its HTTP development setting; Secure mode is checked
on the separate test stack. No new external service/account is used.

## Commands and actual verification
- `npm --prefix frontend test`: **33 tests passed**, zero failures: 12 form, 10 API/session,
  11 new draft tests. New tests cover exact guest input/falsy restoration, field allowlist,
  expiry/corruption/size limits, disabled storage, ordered autosave/manual-save versions,
  snapshot isolation, equivalent-write skipping, 409 blocking, unknown PATCH outcome,
  and disposal while a request is in flight.
- `npm --prefix frontend run build`: TypeScript and Vite production build passed.
- `docker compose build backend frontend`: passed using the actual project Dockerfiles
  and their build stages, both before and after the frontend changes. Normal layer caches
  were used; this was not the previous runtime-only JAR/dist packaging workaround. Docker
  Hub was reachable on this retry. Java was packaged by its Docker build stage; no Java
  source changes required repeating the previous task's 57-test suite here.
- `docker compose up -d --no-build --no-deps backend frontend`: passed; local frontend and
  Java updated to the full images. Main PostgreSQL and FastAPI were not restarted/rebuilt.
- `python3 -m py_compile scripts/check_cookie_https.py`: passed.
- `python3 scripts/check_cookie_https.py`: passed with all six checks true:
  trusted certificate/hostname validation, rejection of an untrusted CA, actual Secure +
  HttpOnly + __Host- + SameSite=Lax cookie attributes, Secure cookie withheld over plain
  HTTP, CSRF rejection/consecutive authenticated create/PATCH writes, logout deleting
  the Secure cookie and subsequent /me returning 401.
- Early disposable-test setup runs exposed Docker internal-network port publication and
  test CA key-usage issues. Fixed the test topology/cert generation while retaining strict
  TLS verification. These runs were cleaned up; no application TLS bug was hidden.
- Post-check Docker inventory confirmed no cookie-https test containers, volumes or
  networks remained. Temporary certificate/key directories were removed. Main stack
  was preserved. Only the redacted boolean result JSON is retained.
- `git diff --check`: passed.

## Browser verification on localhost:3000
1. Open anonymous preliminary form, enter a synthetic amount, description and usage mode;
   F5 immediately after input restored the exact values without login.
2. Sign in through the ordinary modal; the same answers remained visible, a new server
   profile UUID appeared in the URL, and the server-saved notice was shown.
3. Open the existing synthetic final draft from the previous task. Change debt payment
   and collateral values without pressing Save; autosave completed. F5 restored both,
   including the normalized collateral amount returned by Java.
4. Edit debt payment and immediately navigate to Catalog before debounce. Reopening the
   draft restored that new value, proving navigation waited for persistence.
5. Load the same draft in two tabs. First tab saves a new value; second tab attempts a
   stale write and gets a visible conflict. Load current version restores the first tab's
   value. The stale value was not written over it.
6. Browser screenshots record anonymous restoration and final-draft restoration. Native
   beforeunload warning dialogs were not forced during these checks; actual autosave and
   internal navigation were exercised. No real application was submitted or contract signed.

Main-DB smoke artifacts: one additional synthetic preliminary profile and edits to the
existing synthetic unsubmitted draft; the isolated TLS profile/DB was deleted with its
own test stack. No personal data or real financial operation was used.

## Artifacts
- [Anonymous draft after reload](assets/2026-10-26-guest-draft-reload.png)
- [Final application after autosave and reload](assets/2026-10-26-application-autosave-reload.png)
- [HTTPS check result](assets/2026-10-26-cookie-https-result.json)

## Remaining limits
- Guest persistence lasts within the same tab (up to 24 hours since its last local save);
  closing the tab or browser-denied storage prevents that recovery. The UI states this.
- Server autosave requires valid data and connectivity. Before leaving, wait for saved
  state; failures/conflicts are shown and never silently overwrite newer server data.
- TLS verification was on the real disposable local proxy/Java/PostgreSQL stack, not an
  external production domain. Domain routing, public certificate issuance/renewal and
  a production host remain deployment work requiring an actual target.
- ML/scoring implementation/quality and broader MVP work were outside these three fixes.
