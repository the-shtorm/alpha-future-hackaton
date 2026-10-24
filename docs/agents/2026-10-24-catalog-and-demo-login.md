# Catalog and demo login — 2026-10-24

Status: completed. Branch backend-tasks_v2. Separate task report.

## Request

Fix failed demo-owner login and expose a real customer-facing credit catalog with
product cards and details. Resume the unfinished customer UI integration. Preserve
Preliminary Form 2.0 / backend field contract, automatic server-side recommendation
exchange, unknown values and eligibility warnings; do not build a model.

## Findings / work

The configured Docker demo profile had no DEMO_PASSWORD and the demo-owner account
was absent. Set the optional local seed configuration using the already discussed
local test credential; .env is ignored and credentials are omitted from this report.
No existing account password is being reset. Catalog components existed but were
never mounted by the root App and their required styles were missing. Wiring these
into the default public screen, with customer form and saved selections/applications.

## Implemented

- App mounts the public catalog by default; authentication is needed only for saved
  customer data. Header links: catalog, saved selections, applications.
- Catalog loads all 15 active products from the backend. Categories, name search,
  exact decimal amount filtering, purpose and collateral filter, reset/empty/error
  states. Cards show actual amount ranges, terms, rates and collateral. Details dialog
  shows business requirements, guarantees, contributions and actual fees.
- Core Components remain in use; CSS adds customer layout, responsive grids, CSS hero
  artwork, native accessible dialogs, focus states and reduced-motion treatment.
- Wizard now uses only 15 Preliminary Form 2.0 fields. Removed obsolete inputs and
  tax/sector codes; term max 360. Values normalize to exact decimal strings. Login
  resumes the intended form action and binds borrower kind to the chosen company.
- Date input handles native input events, and wizard updates use current state. Browser
  verification caught dates reverting after another field edit; fixed and rechecked
  both visibly and in the stored synthetic profile.
- Saved selections are loaded from backend; no JSON transfer in the customer UI. All
  applicability warnings remain visible. Recsys absence remains honest and does not
  produce scores, percentages or fake recommendations.
- Choosing a checked product creates an application draft. Applications view lists
  customer applications, shows status history, permits editing the 17 answer fields
  (borrower identity remains server-bound), saves financial additions, shows document
  requirements and supports uploads. Submission is separate from saving and requires
  explicit confirmation. No bank approval or model was implemented.
- nginx upload request limit now 11 MB, matching backend multipart allowance for a
  10 MB file. Uploaded documents are shown as received/unverified, not automatically
  accepted by the bank.

## Affected files

frontend/src/App.tsx, styles.css, types.ts, components/{Catalog,Wizard,Selections,UI}.tsx,
new components/Applications.tsx, frontend/nginx.conf, frontend/tests/form.test.mjs.
Updated frontend/README.md, root README and current backend field-contract note.
Local ignored .env config changed for optional demo seed; no credential is included in
reports, screenshots or committed source. Existing backend application code unchanged.

## Actual verification

- `npm --prefix frontend run build`: passed, TypeScript and Vite production build.
- `npm --prefix frontend test`: **7 passed**, no skips. Includes BigInt catalog bounds
  above float-safe range, precise money, unknown/false/zero, removed fields and rates.
- Prettier check of changed frontend sources/tests: passed. `git diff --check`: passed.
- `docker compose up -d backend`: passed, creates the previously absent optional demo
  account from local environment without resetting any existing password.
- `docker compose up -d --build frontend`: final build/start passed. All project services
  running; PostgreSQL/FastAPI healthchecks healthy. `docker compose exec -T frontend
  nginx -t`: configuration syntax passed.
- API smoke through nginx: successful demo-owner login, saved synthetic form, automatic
  selection and retry returning NOT_CONFIGURED with four checked candidates, exact
  applicability conditions and no invented scores/flags. Session logged out afterwards.
- Browser against the actual Docker frontend on port 3000: public 15-product catalog;
  successful demo-owner login; saved-selection listing/opening; checked results and
  unavailable-model notice; begin application; save all four financial additions as
  known zero; success notice. No application submission or bank decision made in QA.
- Browser catalog QA: search returns only matching product; details show actual terms;
  incompatible purpose + no-collateral combination shows empty state; reset restores
  all 15; amount 1,000,000 filters to 11 products. Product CTA prepopulates the form.
- Browser form QA: choose company, seven-sector/tax choices, MSP=false; term 361 rejected,
  12 accepted. Full three-step form sends data and reaches checked products. Stored
  synthetic answers verified as dates 2020-01-01 / 2025-10-01 / 2026-09-30, amount
  1000000.50 and MSP=false. No removed fields or manual JSON controls in the UI.
- Upload smoke through nginx: synthetic 2 MB PDF accepted with HTTP 200 (larger than
  the previous 1 MB proxy limit), draft rowVersion incremented. No bank verification.
- Screenshots: assets/2026-10-24-catalog-home.png and 2026-10-24-catalog-cards.png.
  Browser tab left on the unfiltered catalog. Responsive CSS implemented; physical
  mobile/viewport validation not performed. No claim of a mobile browser QA pass.

## Limits and Git state

Recsys HTTP endpoint remains absent. Bank operations UI, real e-signature and actual
fund disbursement are outside this change. Backend policy/models were not changed.
Existing backend tests passed in the preceding build-fix task (45); not rerun for this
frontend/configuration-only task. Synthetic QA profiles, one draft and test document
remain in the local demo database; no real customer data used or deleted.

Branch backend-tasks_v2; no commit or push requested/performed. Earlier uncommitted
changes preserved. Completed prior task reports left unchanged; this task has its own
report. The former paused customer-UI work is continued here.
