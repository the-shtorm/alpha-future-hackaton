# Interface animations — 2026-10-24

Status: completed. Branch backend-tasks_v2. No commit or push.

## Request and scope

Add customer interface animations. Preserve existing form validation, financial rules,
data and interactions. No new runtime dependencies or backend changes in this task.
Previous form-controls changes are still uncommitted and must be preserved.

## Implementation

Finite CSS entry animations for pages, hero, product/saved cards, wizard steps,
application content, dialogs, dropdowns, notices and expanded details. Small hover
feedback on cards/arrows and transitions for selected options/progress. Step content
is keyed by step so the entrance repeats on navigation, not on typing or validation.
Animations run only with prefers-reduced-motion: no-preference; no interaction waits
for an animation or timer. No automatic scrolling animation or infinite decoration.

## Files and contract impact

- `frontend/src/styles.css`: entry keyframes, short stagger (0/45/90 ms), popup and
  backdrop entry, hover and selection feedback; all new motion is inside the
  no-preference media query. Durations range from 140 to 420 ms.
- `frontend/src/components/Wizard.tsx`: keyed step-content wrapper; headings and
  fields enter together on changing steps. Buttons/progress stay mounted.
- `frontend/src/components/Applications.tsx`: keyed application layout for entry
  when opening another application.
- This report, shared task index and frontend README.

No API, schema, financial rule or migration changes. No animation library or timer
was added. Existing reduced-motion overrides are retained. Closing dialogs remains
immediate; this task adds entry animations, not delayed unmount/exit transitions.

## Actual verification

- `npm --prefix frontend run build`: TypeScript and production Vite build passed.
- `npm --prefix frontend test`: 11 tests passed, no failures.
- `docker compose up -d --build frontend`: build/start passed; frontend recreated,
  existing backend and PostgreSQL remained running. Port 3000 unchanged.
- Browser verified the new CSS bundle (`index-DhX3zDm1.css`) and actual computed
  animations: page surface-enter; step/dialog content-enter (dialog 220 ms);
  popup-enter (140 ms); first three product-card delays 0/45/90 ms.
- Dialog opacity observed at entry 0 then at rest 1 with translate none. Product
  details opened and closed with Escape; login dialog opened and closed by its button.
- Form sector selected by mouse, start date entered; steps 1→2→3→2 work and a
  synthetic 1,000,000 amount survives returning. Input retained focus while typing;
  step remained at rest, with no repeated animation on keystrokes.
- Form and popup were visually inspected in the rebuilt browser. Proof:
  [form](assets/2026-10-24-animated-form.png),
  [dialog](assets/2026-10-24-animated-dialog.png).

Reduced-motion exclusion was checked in source; the browser ran with its default
no-preference setting. No separate reduced-motion emulation or mobile browser test.
Backend tests were not rerun because this task changes only frontend presentation;
the previous task's 48-test result remains documented in its own report.

Existing uncommitted work from the preceding form-controls task is preserved.
