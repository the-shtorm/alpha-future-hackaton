# Smooth catalog anchor navigation — 2026-10-25

Completed on backend-tasks_v2. User reported an abrupt transition from the hero's
«Смотреть каталог ↓» link.

Cause: the native `href="#catalog"` anchor had no smooth-scroll behavior. Added
`html { scroll-behavior: smooth; }` inside the existing no-preference motion media
query in `frontend/src/styles.css`. Native anchor/hash semantics are preserved;
explicit instant page/step resets remain instant. Existing reduced-motion rules
keep scrolling immediate when reduced motion is requested. No JS animation loop,
dependency, backend, API or data change.

Verification:

- `npm --prefix frontend run build`: TypeScript and Vite production build passed.
- `git diff --check`: passed.
- `docker compose up -d --no-deps --build frontend`: passed; only frontend recreated.
- Browser loaded `index-IJnbRqtn.css`; root computed scrollBehavior was smooth.
  Anchor activation set #catalog while scrollY initially stayed at 22; the next
  observation showed scrollY 671 and catalog top 25px, matching its scroll margin.
  This verifies a gradual scroll rather than an immediate destination jump.
- Mouse automation encountered a dispatch timeout; the same native link was then
  activated successfully with Enter. No separate reduced-motion emulation performed.
- [Destination screenshot](assets/2026-10-25-catalog-smooth-scroll.png).

No new tests for this small CSS-only correction; no commit or push.
