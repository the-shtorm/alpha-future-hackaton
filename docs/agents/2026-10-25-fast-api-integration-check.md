# fast_api integration verification and repairs

## Request and scope
Verify the merged backend on `fast_api`, fix compatibility problems, and verify the complete form-to-recommendations journey, including available application and infrastructure checks.

## Initial state
- Branch: `fast_api`, tracking `origin/fast_api`; working tree initially clean.
- Repository instructions read; no nested AGENTS.md found by file inventory.
- Investigation and validation in progress. No application checks claimed yet.

## Findings and repairs
- Existing `.env` lacked `RECSYS_API_KEY`, so Compose interpolation failed. Generated a random shared internal key in the ignored local `.env`, preserving existing settings; no secret values are recorded here. File permissions are 0600.
- The running FastAPI image was the old scaffold exposing only `/health`, with no ranking or torch dependencies. Built current Java, frontend and actual CPU E5 images, then recreated local application containers.
- The checkpoint was a 134-byte Git LFS pointer. Downloaded Git LFS 3.7.1 from its official GitHub release, installed the executable in the existing user PATH directory, enabled LFS locally for this repository, and downloaded/checked out the 471 MB checkpoint. The tracked model content is unchanged after the LFS filter; no new weights were trained.
- Fedora SELinux denied the container access to the mounted checkpoint (`PermissionError`); this caused ML initialization to fail and blocked dependent services. Changed model bind mounts to `ro,z` in `compose.yaml` and `compose.ml-test.yaml`. The disposable test stack's PostgreSQL init scripts also use `ro,z`. The shared label allows concurrent checks of the same read-only checkpoint. After this repair offline model verification and startup passed.
- `fastapi/scripts/java_acceptance.py` now reads its model lock with the standard library, so host orchestration needs no Pydantic/torch installation. Expanded the existing real HTTP acceptance flow to verify saved-selection listing/restoration, selected-product PUT, draft application creation/readback, preservation of the requested amount, and continued validity after product choice. Existing checks cover unchanged eligibility/pending conditions, model identity, threshold, complete candidate ranking, idempotent retry/import, and stale import rejection.
- `frontend/src/components/Selections.tsx`: a successful ranking with zero recommended candidates no longer claims that personalized offers were highlighted. Eligible products remain visible.
- README corrects startup key instructions, private ML-port documentation, V11 description and stale statements that the model is not integrated. `docs/validation.md` links current evidence and documents how to rerun the disposable acceptance stack.

## Contracts and migrations
- No API schema, model identity, selection threshold, financial decision rules or database migration changed.
- Existing migrations V1–V11 plus two demo repeatables validated successfully against the existing database (13 migrations); schema was already at V11. A fresh database was also initialized by the acceptance stacks.
- The model performs semantic ordering and recommendation selection. Financial credit assessment, offers/signatures/disbursement remain the existing DEMO implementation.

## Commands and actual results
- `git status --short --branch` and file inventory: verified branch and initial clean state; no branch switch, commit, merge or push performed.
- `npm --prefix frontend test`: 11 passed; repeated after UI text change, 11 passed.
- `npm --prefix frontend run build`: TypeScript and Vite passed before and after UI change.
- `mvn -f backend/pom.xml -Dmaven.repo.local=/tmp/alpha-credit-m2 --batch-mode --no-transfer-progress verify javadoc:javadoc`: initial sandboxed attempt could not access Docker. Repeated with Docker access: BUILD SUCCESS; 52 tests, zero failures/errors/skips (28 integration, 12 policy, 7 eligibility, 5 form); Spotless and JavaDoc passed.
- `docker build --target test -t alpha-future-fastapi:integration-test fastapi`, `docker compose build backend frontend`, `docker compose build fastapi`: passed after granting Docker access. Initial sandboxed Docker build failed on socket permissions.
- `docker run --rm alpha-future-fastapi:integration-test python -m pytest`: 169 passed, 2 skipped, 100% application branch coverage; skipped tests are real base/finetuned model tests, handled separately below for the active finetuned variant.
- Runtime `python -m scripts.verify_model --model-path /models/active --smoke`: initial unlabeled bind mount failed under SELinux; repeat with `ro,z` passed. Verified 9 files, pinned artifact SHA, normalized float32 CPU embeddings of shape `[2,384]`.
- Real-model pytest in the test image with mounted weights, `RUN_REAL_MODEL_TESTS=1`, `RUN_FINETUNED_MODEL_TESTS=1`, `FINETUNED_MODEL_LOCAL_PATH=/models/active`, `python -m pytest tests/integration/test_real_model.py -k finetuned --no-cov`: 1 passed, 1 deselected. Confirms both native and Java HTTP adapters with actual E5 and rejects excessive token length.
- From `fastapi/`: `ML_TEST_IMAGE=alpha-future-fastapi:local ML_TEST_BACKEND_IMAGE=alpha-future-backend:local python3 -m scripts.java_acceptance --model-variant finetuned --output /tmp/fast-api-java-e2e.json`: passed initially and after adding draft/saved-selection assertions. Conditional, unknown-context and logistics scenarios each returned READY, 4 candidates and 3 recommendations; empty scenario returned EMPTY and no candidates. Stale import returned 409 as expected.
- Same acceptance command with `--max-cosine-distance 0 --output /tmp/fast-api-java-zero-recommendations.json`: passed; non-empty cases retain all 4 candidates with 0 recommendations. The normal application's threshold was unchanged.
- `/tmp/fast-api-live-check.py`: first sandboxed HTTP attempt was denied socket access; rerun with localhost access passed. Uses the actual `normalizeAnswers(exampleAnswers())` payload from `frontend/src/form.ts`, existing demo login and nginx `/api`. Catalog has 15 products; automatic selection returned READY, 4 candidates, 3 recommendations in 0.381 seconds (single local observation, not a benchmark). Saved result restored, product selected, draft created/read with amount preserved; this HTTP test session was logged out.
- Browser: traversed all three form steps with synthetic input, completed demo login, saw four result cards and three recommendation badges with pending conditions, then clicked Start application and observed a draft with the selected product and transferred amount. One attempt overlapped the frontend container replacement and showed a connection error; retry after deployment completed succeeded. Refresh confirmed the existing loss of frontend login state.
- `docker run ... alpha-future-fastapi:integration-test ruff check app scripts tests`, mounting current scripts: passed, including final script changes.
- `docker compose config --quiet` and dev override equivalent: passed. Final `docker compose ps`: frontend running on localhost:3000, backend on localhost:8081 (existing configuration), FastAPI healthy on the private network, PostgreSQL healthy, pgAdmin unchanged. No `recsys-java-*` test containers remain; acceptance stacks removed their own test volumes.
- `git diff --check`: passed. Git checks after LFS checkout needed access to `.git/lfs/tmp` outside the read-only sandbox; final checks succeeded with that access.

## Evidence
Sanitized artifacts in [artifacts/2026-10-25-fast-api-integration](artifacts/2026-10-25-fast-api-integration/):
- [Real Java/E5 acceptance](artifacts/2026-10-25-fast-api-integration/java-e2e.json).
- [Zero-recommendation acceptance](artifacts/2026-10-25-fast-api-integration/zero-recommendations.json).
- [Live nginx/form/draft check](artifacts/2026-10-25-fast-api-integration/live-proxy.json).
- [Verified model package](artifacts/2026-10-25-fast-api-integration/model-package.json).
- [Browser recommendations](artifacts/2026-10-25-fast-api-integration/recommendations.png) and [draft](artifacts/2026-10-25-fast-api-integration/draft.png).

Local command logs are `/tmp/fast-api-integration-backend.log`, `/tmp/fast-api-integration-pytest.log`, `/tmp/fast-api-real-model-tests.log`, `/tmp/fast-api-integration-model.log`, `/tmp/fast-api-java-e2e.log`, `/tmp/fast-api-java-zero-recommendations.log`, and build/start logs with the `fast-api-` prefix. No credentials or full questionnaire contents were added to the report or committed evidence.

## Remaining issues and verification limits
- Frontend authentication is held only in React state: refreshing loses login and unsaved form state. Saved profiles/results and created drafts remain in PostgreSQL and can be reopened after login. Confirmed in browser; unchanged in this task.
- The banking workflow has backend endpoints/tests but no banking UI in the current frontend. A full browser journey through bank review cannot be completed with this interface.
- Financial assessment, signature and payment/disbursement behavior remain explicitly DEMO; real scoring, legal signature and money-transfer integrations are not implemented. A current bank macro context must be entered through the existing API for the corresponding demo decision paths.
- E5 and its threshold are calibrated on synthetic labels; working integration does not establish suitability on real bank customers. No expert validation or independent real-world quality study was performed.
- The base E5 variant was not downloaded/tested here; the deployed finetuned variant was tested with its real weights. No load test or complete manual browser exercise of every application/bank/document branch was performed; the backend integration suite covers its existing workflow scenarios.
- Non-fatal library deprecations remain: SentenceTransformers embedding-dimension method rename and Starlette's httpx TestClient warning. Tests and active inference pass.

## Final state
Completed for the form/recommendation/product/draft integration scope. Changed tracked files: README.md, compose.yaml, compose.ml-test.yaml, docs/validation.md, docs/agents/log.md, fastapi/scripts/java_acceptance.py, frontend/src/components/Selections.tsx; new report and sanitized evidence directory. Local `.env` updated and weights hydrated (ignored/local infrastructure changes). Two synthetic profiles/drafts were created in the running demo database by the HTTP/browser checks; isolated acceptance data was removed with its own stacks. All changes are uncommitted on `fast_api`; nothing pushed.
