# Form controls, alignment and basic validation — 2026-10-24

Status: completed. Branch backend-tasks_v2. Changes are local; no commit or push.

## Request / decisions

Fix arrow positioning in buttons including catalog CTAs; center form with its summary;
replace overlapping square native select/focus borders; prevent absurd amounts/low
known revenue from yielding financing offers. Use existing product limits and revenue
rules, not an invented loan-to-revenue multiplier or a model.

## Work

Library-aligned icon addons, centered 1120px form wrapper, accessible custom rounded
combobox/listbox. Frontend field/catalog validation and explicit full-month period when
revenue is supplied. Server enforces the same period completeness before eligibility;
low known revenue remains a valid fact leading to product exclusion, not a fake input
correction. Unknown revenue stays unknown. Eligibility 3.1 invalidates older runs for
new selection/ranking/application transfer while retaining immutable history.

## Files / contract impact

- `frontend/src/components/UI.tsx`, `styles.css`: shared rounded combobox/listbox,
  keyboard navigation, text search, outside click/Escape closing and a single focus
  ring in both preliminary form and application; centered form including summary.
- `App.tsx`, `Catalog.tsx`, `Wizard.tsx`, `Applications.tsx`, `Selections.tsx`: icons
  use Core Button addons with proper spacing/alignment. Selection empty state explains
  catalog amount/revenue exclusions; stale results prompt another check.
- `frontend/src/validation.ts`, `tests/form.test.mjs`: exact-money/catalog bounds,
  date/term/description and revenue-period checks, including final-step revalidation.
- `FormPolicy.java`, `Eligibility.java`, `SelectionProfiles.java`, `RankingExchange.java`:
  reject missing/non-full revenue periods before matching, explicit revenue reasons,
  eligibility-3.1 freshness guards for product selection, ranking and application transfer.
- `BackendIntegrationTest.java`: direct-API regressions for tiny revenue, huge amounts,
  incomplete periods and old policy runs. API/field docs and frontend README updated.

Root cause: supplied revenue without a usable period was treated as unknown by the
existing monthly-revenue calculation. This allowed conditional candidates instead of
excluding products with minimum revenue requirements. A supplied amount now requires
an interpretable period before matching. Blank revenue still means unknown; no arbitrary
loan-to-income ratio was added. Existing product amount/revenue limits remain authoritative.

No database migration or historical data rewrite. Partial drafts remain saveable.
Old eligibility runs remain readable but cannot be reused for a new choice, ranking
exchange or application; callers receive 409 SELECTION_STALE and must repeat matching.
No model, model training, fake recommendations, credential or `.env` changes.

## Actual verification

- `npm --prefix frontend test`: 11 passed, 0 failed.
- `npm --prefix frontend run build`: TypeScript and production Vite build passed.
- `mvn -f backend/pom.xml -Dmaven.repo.local=/tmp/alpha-credit-m2 --batch-mode --no-transfer-progress verify javadoc:javadoc`:
  48 tests passed, 0 failures/errors/skips; style, JAR build and JavaDoc passed.
- `docker compose up -d --build frontend backend`: both images rebuilt and containers
  recreated successfully, existing PostgreSQL volume retained. UI remains on port 3000.
- Browser checks against the rebuilt containers: equal horizontal form margins with
  its summary; rounded popup; selection by mouse and keyboard; Escape and outside-click
  closing in an application without saving or submitting that application. Hero and
  catalog arrow centers equal the respective button vertical centers in DOM measurements.
- Huge requested amount `12121212121200000` is blocked on step 2 with actual catalog
  bounds (100,000–30,000,000 RUB). Revenue 10 without dates is blocked on step 3.
  Revenue 10 for 2025-10-01 through 2026-09-30 with a 1,000,000 RUB request returns
  no eligible products and an explicit revenue reason. Synthetic local demo data only.
- Direct-API tests also confirm empty results and all 15 revenue exclusions for tiny
  known revenue, including an oversized request; excluded products cannot be chosen.

Proof screenshots:

- [Centered form and select](assets/2026-10-24-centered-form-select.png)
- [Catalog buttons](assets/2026-10-24-catalog-button-alignment.png)
- [Application select](assets/2026-10-24-application-select.png)
- [Amount validation](assets/2026-10-24-amount-validation.png)
- [Low revenue: no offers](assets/2026-10-24-low-revenue-no-offers.png)

Browser QA used the desktop viewport; no separate mobile browser check was performed.
Recsys remains unconfigured; this task changes validation and applicability checks,
not recommendation scoring or bank approval.
