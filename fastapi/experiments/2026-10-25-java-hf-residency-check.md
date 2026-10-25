# Java contract and HF model residency verification

Date: 2026-10-25. Branch: fast_api, code commit 13cdf19.

## Request and constraints

Check current Java compatibility, real HF download, and local model reuse.
No GitHub push, no changes to docs/ or draft.ipynb, no restart of the user's
working stack. This new report is outside docs/agents/ to honor the user's
instruction not to edit docs. No production code changes were necessary.

## Java contract

Read the current RecsysGateway, AutomaticSelection, RankingExchange,
RankingVocabulary and ProductSemantics Java sources, docs/ranking-exchange.md,
docs/contracts/ranking-response.schema.json, and FastAPI DTO/adapter/routes.
The Java-owned response JSON Schema and the shipped FastAPI response schema
match. Historical docs still mention an exact top-three requirement and an
unfinished HTTP adapter; current Java code implements HTTP and accepts 0..topK
recommended prefix items, maximum three. Documentation was not changed.

Confirmed endpoint POST /api/v1/recommendations/rank-java with Bearer auth,
query-passage-mvp-2 and synthetic-semantics-1 versions, UUID identifiers,
six projected query fields, product semantics and LOGISTICS/TRANSPORT mapping.
Response contains every candidate, preserves product versions, eligibility and
full ordered conditions, and returns exactly the four Java metadata fields.

Command run from fastapi/:

```powershell
.venv/Scripts/python.exe -m pytest tests/api/test_java_exchange.py tests/unit/test_contract_snapshots.py tests/unit/test_model_path.py tests/unit/test_model_source.py -o addopts='' -q --junitxml=reports/java-hf-contract-check.xml
```

Result: 50 passed, one skipped (Windows test symlink privilege), zero failures.
This focused run does not replace or overwrite the previous full coverage run.

Built the current Java backend Docker image successfully, then ran
scripts.java_acceptance --model-variant finetuned using the current
alpha-future-fastapi:model-path image and the model files just downloaded from
HF. This separate temporary Java/Postgres/FastAPI stack was removed afterward.
It did not replace the user's working containers.

Actual Java HTTP gateway -> CPU E5 -> Java validation/import results:

| Case | Status | All candidates | Recommended |
|---|---|---:|---:|
| Conditional security | READY | 4 | 3 |
| Missing optional context | READY | 4 | 3 |
| LOGISTICS sector | READY | 4 | 3 |
| No eligible products | EMPTY | 0 | 0 |

Idempotent retry/import, stale import rejection (409), metadata identity and
unchanged conditions/version/status checks passed. Container memory snapshot:
768 MiB / 2 GiB. Report: work/ml-acceptance/java-hf-artifact-e2e.json.
The Java chain mounts the freshly downloaded HF snapshot as local files; the
separate download/residency check below exercises MODEL_PATH=HF directly.

## Real HF download, RAM and disk cache

Executed work/ml-acceptance/verify_hf_java_residency.py with a previously absent
models/hf-java-residency-verification cache and MODEL_PATH set to the short
thedauns/e5-credit-finetune-v1 name. It resolved the pinned HF revision
e93f86ce54f0a6d2b3da24dac803e50ee92bbb2b, downloaded ten files (33.5 s observed
transfer), initialized the real model and passed three inference requests.
The initial offline-restart guard also blocked Windows asyncio's own loopback
socketpair. This was a verification-harness issue; it was adjusted to permit
loopback while rejecting all external connections. The complete check was then
rerun with --reuse-cache, so its final JSON correctly reports an existing cache.

Weights: 470637416 bytes; SHA-256
502f9765a9cebed997794d64dcdc905721d0ca7b0c47a66262f227ea42a63b4c.
Runtime artifact SHA-256:
116acca8c00237091e511ea6e96a2959ad1345d9439b8c5a9c7fc2c29b9012e8.

Measured in the completed instrumented run:

- One snapshot resolver invocation and one SentenceTransformer initialization
  at startup. Further resolver/constructor calls were configured to fail.
- Three distinct Java requests: HTTP 200 for all, three ranked candidates each,
  recommended counts 1, 1 and 0. Every reply validated against Java's own schema.
- External network blocked during inference; zero socket connection attempts.
- Same model object and every parameter's tensor storage pointer before/after
  requests. CPU parameters occupy 470615040 bytes. No request-time model reload.
- Real Russian encodings: dimension 384, finite values and unit norms.
- Windows process RSS: 1188.43 MiB after startup, 1203.85 MiB after requests.
  These are smoke measurements, not a complete benchmark.
- A new app lifespan with HF_LOCAL_FILES_ONLY=true loaded the same disk cache
  and returned HTTP 200 with zero external network attempts.

The model object stays in process RAM for its lifetime. The HF files remain on
disk; a process restart loads them into RAM again. Compose mounts /model-cache
as a persistent named volume, so ordinary container recreation preserves it.
Report: work/ml-acceptance/hf-java-residency-verification.json.

## Important: current working deployment

Read-only inspection of alpha-future-hackaton-fastapi-1 found an older image,
no MODEL_PATH environment variable, MODEL_LOCAL_PATH=/models/active and
MODEL_VARIANT=finetuned. Its live model-info confirms the correct fine-tuned
artifact SHA and maxCosineDistance=0.5237781852483749. It currently loads from
local disk. The successful HF checks above were isolated verification runs.

To select HF in that deployment, set MODEL_PATH in the root .env and supply
HF_TOKEN as a read secret for the private repository, then rebuild/recreate
only the FastAPI service. HF CLI authentication on Windows is not automatically
passed into Docker. This deployment change was not performed during a request
to check compatibility.

## Git

No production code, contracts, docs, weights, thresholds or secrets changed.
Only this new report is added to the working tree. Test reports, downloaded
cache and verification harness remain ignored. Nothing committed or pushed
as part of this verification task.
