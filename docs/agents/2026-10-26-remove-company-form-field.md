# Remove the company selector from the preliminary form

## Request and constraints
Remove the company field from the form. Keep the existing authorized account/company association required for saving profiles and applications. Starting branch cookie-session, HEAD 2d9c0ab, clean working tree.

## Changes
Removed the Company dropdown from Wizard, its party-selection props and the now-unused changeParty handler in App. Wizard receives only the existing business-kind lock flag. New forms retain the account's default writable company; reopened saved forms retain their stored company. Backend partyId, ownership rules and API/data contracts are unchanged.

## Verification
- `npm test`: 34 existing frontend tests passed (13 form, 10 session, 11 drafts).
- `npm run build`: TypeScript/Vite passed, asset index-Cud-_zl4.js.
- `git diff --check`: passed. No new tests added for this small UI deletion; backend contracts did not change.
- Standard Docker frontend build failed retrieving node:22-alpine metadata because Docker Hub was unreachable. Built an offline image successfully from the existing local nginx frontend image plus the verified dist output. The first offline attempt used the frontend context, where dist is excluded by .dockerignore; using dist itself as the build context succeeded.
- Local deployment check found the main backend was not running and no existing main-project containers were present. Standalone frontend nginx could not resolve backend. Removed only the frontend container and empty networks created by this check, restoring the stopped-stack state; no data volumes were removed. Browser/API pipeline checks were not performed for this task. Updated frontend source and local image are ready for the next normal stack startup.

## Git
No branch changes, merge, commit or push requested/performed. This task's changes are uncommitted.
