# Backend field alignment — 2026-10-24

Status: completed (backend field contract only). Branch backend-tasks_v2. No commit or push requested.

## Request and sources

Pause customer frontend redesign. Align backend fields with corrected Data Policy 3.0,
Preliminary Form 2.0 and Query/Passage MVP. Exclude dataset analysis as the governing
contract; do not implement a model. Source copies are in docs/reference/.

## Decisions and implementation

Explicit field lists govern the inconsistent counts: 15 preliminary / 13 transferred /
17 final, rather than source headings 14/12/16. See docs/backend-fields-v3.md for types,
unknown values, required selection fields, editable legacy upgrades and exact scope.
Removed six obsolete form fields. New enums, 1..360 integer term, exact two-decimal
money/percent, consistent validation in both stages, voluntary collateral completeness,
actual-start-only tenure, usage compatibility, separate review of uncollected conditions.
Catalog exposes type/interestRateType/usageModes. Two append-only synthetic product
versions replace INVESTMENT with DEVELOPMENT; latest active version only is listed.
Legacy profiles require explicit PATCH upgrade before new selection. Immutable historical
runs/revisions remain intact. Application revisions now store application-3.0 schema.

No ML, SBA preprocessing, FX/NAICS mapping or new decision algorithm. Existing 2.1
financial/DEMO behavior remains explicitly distinguished from the 3.0 field schema.
Frontend and prior automatic-adapter work stay paused and are not claimed complete.

## Files and compatibility

- backend/src/main/java/ru/alphafuture/credit/{FormPolicy,RankingVocabulary,
  SelectionProfiles,RankingExchange,Eligibility,ApplicationService,CabinetController,
  Catalog,DataPolicy,ProductSemantics,DemoScenarios}.java.
- backend/src/main/resources/db/demo/R__zz_form_v3_product_purposes.sql: new append-only
  demo seed after the original catalog. No existing numbered migration rewritten.
- TestData, DataPolicyTest, EligibilityTest, BackendIntegrationTest, new FormContractTest.
- docs/backend-fields-v3.md is the authoritative implemented field contract. Updated
  README and API, Postman, storage, data dictionary and ranking docs link to it;
  historical policy/form sources are marked as historical. Original revised user
  documents are copied unchanged to docs/reference/. Two JSON examples are in
  docs/contracts/. Completed prior reports remain unchanged; paused task report
  records the user’s scope change.

An editable application reports formVersion. Legacy inheritance occurs only while
upgrading an old application; later saves never resurrect cleared/unknown answers
from preliminaryContext. New snapshots store the schema version independently from
existing financial policyVersion=data-policy-2.1. Existing records are not bulk changed.
The two synthetic catalog cards get new version IDs; old versions and snapshots stay
readable. New catalog selection returns only the latest effective version per product.

## Actual verification

- `mvn -f backend/pom.xml -Dmaven.repo.local=/tmp/alpha-credit-m2 --batch-mode
  --no-transfer-progress spotless:apply test-compile`: passed.
- `mvn -f backend/pom.xml -Dmaven.repo.local=/tmp/alpha-credit-m2 --batch-mode
  --no-transfer-progress verify javadoc:javadoc`: passed. **44 tests, 0 failures,
  0 errors, 0 skipped**: 20 PostgreSQL/API integration + 12 DataPolicy + 7 Eligibility
  + 5 field-contract tests. Spotless, executable JAR build and JavaDoc passed.
- Integration uses disposable PostgreSQL 17 Testcontainers with runtime-role grants.
  New tests cover schema/dictionaries/catalog endpoints, 15/13/17 fields, old-profile
  upgrade and immutable old run, old-application upgrade, unknown data surviving later
  edits, exact term/money types, both-stage enums, collateral completeness and shared
  fields. Catalog test verifies all active purposes belong to the new vocabulary and
  both original INVESTMENT versions remain stored unchanged.
- Initial sandbox integration attempt could not access Docker; rerun used the already
  approved Maven/Docker access. Earlier runs exposed old test expectations and the
  unknown-value inheritance bug; both were fixed and the complete suite rerun above.
- `git diff --check`: passed. Source copies and JSON examples checked locally.

## Limits and Git state

Branch backend-tasks_v2. Changes are uncommitted; no commit/push or new branch created.
The workspace already contained prior uncommitted backend/frontend/infra edits; these
were preserved. No production volumes, running application services or user .env changed.
Only test containers and the local build were run. Existing previews therefore continue
running their previously started builds until explicitly rebuilt/restarted.

No frontend edits or frontend build in this task: redesign is paused and unfinished,
and its old questionnaire still needs migration to the new backend schema. No claim
that this paused frontend or its automatic HTTP adapter is complete. Recsys has no
endpoint; no external model call, training or fabricated ranking was introduced here.
Full hybrid financial decision algorithm 3.0 remains outside this field-only task.
