# Frontend / Docker Compose build fix — 2026-10-24

Status: completed (build repair and active-form compatibility). Branch backend-tasks_v2. New report for this task.

## Request and cause

The user pasted a failed `docker compose up -d --build`. TypeScript failed because
App.tsx still imported removed downloadJson, Packet and Ranking while shared frontend
modules had already changed during a paused redesign. This inconsistency was left by
previous work. Backend build was cancelled by Compose after the frontend error.

## Scope and changes

Repair the active frontend rather than restoring manual JSON exchange. App uses the
existing automatic-selection/retry API and Selection/Candidate types. No model or fake
ranking: absent Recsys returns checked products with an honest unavailable notice.
Manual JSON export/import/file resume controls were removed from the active UI.
The paused catalog/cabinet redesign is not claimed complete.

The active form now matches preliminary-2.0: 15 fields, seven sectors, eight purposes,
1..360 month term, current tax regimes, no removed geographic/registration/counter
fields. Money normalization uses strings and exact two decimals; known zero/false and
unknown/null remain distinct. Obsolete fields in legacy form data are filtered. Business
kind follows the authenticated company's kind. Technical cosine values stay out of the
customer cards. Fixed rate formatting so an integer 20% does not become 2%.

Files: frontend/src/App.tsx, frontend/src/form.ts, frontend/src/presentation.ts,
frontend/tests/form.test.mjs. Added one BackendIntegrationTest for the automatic
selection/retry API with Recsys explicitly unconfigured. This report and docs/agents/log.md.

## Actual verification

- `npm --prefix frontend run build`: passed, TypeScript and Vite production bundle.
- `npm --prefix frontend test`: **6 passed**, including exact money, missing values,
  removed fields, synthetic form, and integer rate formatting.
- Prettier applied to changed frontend files; `git diff --check` passed.
- `mvn -f backend/pom.xml -Dmaven.repo.local=/tmp/alpha-credit-m2 --batch-mode
  --no-transfer-progress verify javadoc:javadoc`: **45 passed**, no failures/errors/
  skips. Spotless, JAR packaging and JavaDoc passed. New integration test verifies
  automatic selection and retry return NOT_CONFIGURED, preserve eligibility conditions
  and full product terms, and never invent scores or recommendation flags.
- The user's exact `docker compose up -d --build`: **exit 0**. All three images built;
  frontend/backend/FastAPI/Postgres/pgAdmin containers running. Postgres and FastAPI
  healthchecks healthy. Existing Compose configuration and volumes retained.
- Local HTTP smoke: frontend nginx `/api/products` returned HTTP 200 and 15 catalog
  products; FastAPI `/health` returned status ok. Frontend is reachable on port 3000;
  backend uses the existing configured host port 8081, not the default 8080.
- Browser opened the actual Docker-served page on localhost:3000 and verified the
  first-step current-sector form and absence of removed geographic/counter fields and
  manual JSON controls. No authenticated browser flow claimed.
- Optional authenticated live smoke was skipped because no DEMO_PASSWORD was configured
  in local .env; no credentials were added or printed. The authenticated automatic
  selection scenario was verified by the isolated PostgreSQL integration test instead.
- Initial Docker-socket/localhost smoke attempts were denied by sandbox isolation;
  reruns used the existing approved Docker/local-network access.

## Limits and Git

No model, fabricated ranking, new credentials, backend production logic or numbered
migration was added. Recsys remains unconfigured; the UI says personal selection is
unavailable and shows eligibility-checked products. Full catalog/cabinet redesign remains
paused; this task repairs the active form rather than claiming that redesign complete.
Compose startup applies existing pending migrations through the normal backend startup.
No database volume was reset/deleted. No user .env was edited.

Branch backend-tasks_v2. Changes are uncommitted; no push was requested/performed.
