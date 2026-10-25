# E5: Hugging Face publication and one MODEL_PATH

## Request and constraints

Host the final E5 model and its supporting artifacts in private HF organization
`thedauns`; keep large assets out of the current Git tree. Select local disk,
Hugging Face or future S3 storage through one `MODEL_PATH` in `.env`.
S3 compatibility only: no bucket was created and nothing was uploaded to S3.
No GitHub push. User requested no changes to `docs/` or `draft.ipynb`, so this
report is outside `docs/agents/` and those files remain unchanged.

## Delivered

- Private repository: https://huggingface.co/thedauns/e5-credit-finetune-v1
- Latest supporting package: HF commit
  `4c038b1aa06a49cd9f5019f7f706bc8e381568a3`, 104 files, verified remotely.
- Runtime model transport remains pinned to
  `e93f86ce54f0a6d2b3da24dac803e50ee92bbb2b`; subsequent commits only update
  supporting files. All model bytes are unchanged.
- Artifact SHA-256:
  `116acca8c00237091e511ea6e96a2959ad1345d9439b8c5a9c7fc2c29b9012e8`.
- Weights SHA-256:
  `502f9765a9cebed997794d64dcdc905721d0ca7b0c47a66262f227ea42a63b4c`.

`model/` contains the ten final inference files. `service/` includes application
and preparation/training scripts, dependency locks, templates/vocabulary, API
schemas/examples, synthetic datasets and training metadata. Root model card and
package manifest describe contents and SHA-256 checksums. Secrets, `.env`, caches,
environments, optimizer state and intermediate checkpoints are excluded.

Source alternatives, each using just MODEL_PATH:

```dotenv
MODEL_PATH=thedauns/e5-credit-finetune-v1
# MODEL_PATH=hf://thedauns/e5-credit-finetune-v1@e93f86ce54f0a6d2b3da24dac803e50ee92bbb2b/model
# MODEL_PATH=C:/models/e5-credit-finetune-v1/final
# MODEL_PATH=/srv/models/e5-credit-finetune-v1/final
# MODEL_PATH=s3://bucket/prefix
```

The known short HF name resolves through `config/hf-deployment.lock.json`.
Other HF repositories require an immutable SHA in the hf:// value. Relative
local paths may start with `./`. In Compose the local mount is `/models/...`.
MODEL_PATH overrides retained legacy source settings. Authentication is separate:
HF_TOKEN for private HF; standard AWS credentials/IAM and optional S3_ENDPOINT_URL
for compatible S3. Tokens are never embedded in MODEL_PATH or committed.

Settings loads `fastapi/.env`; process environment takes precedence. Startup
resolves/downloads once, validates the pinned model manifest and every checksum,
then loads the local CPU model. No automatic fallback. Existing ranking, F1
threshold, API and Java metadata remain unchanged. Linux HF snapshot links are
materialized into regular files before strict manifest validation.

Compose has a writable persistent model cache and outbound access for downloads;
runtime remains non-root/read-only. boto3 is added to the genuine uv.lock, CPU
PyTorch source retained, requirements exports refreshed. Manual CI accepts
MODEL_PATH and source credentials; regular CI uses fake encoders without weights.
MODEL_HANDOFF.md contains deployment and repeat-publication instructions.

## Verification

- Full pytest including both real models: 202 passed, 1 skipped, 0 failures
  (`reports/model-path-tests.xml`, 45.373 s). Windows cannot create test symlinks;
  that case passed separately under WSL/Linux.
- Coverage: 872/899 lines, 192/208 branches; combined approximately 96.12%, above
  required 95%. Ruff check and format check passed for 75 files.
- `uv lock --check --offline`: 72 packages resolved, lock valid.
- Final package checker tests after message-only cleanup: 2 passed.
- Fresh authenticated private HF download, real CPU startup, core and Java HTTP
  requests, and cache-only restart passed. One canonical MODEL_PATH alone also
  passed real HF startup and Java HTTP 200. Reports are in ignored
  `work/ml-acceptance/hf-source-acceptance.json` and `single-model-path-smoke.json`.
- Mocked S3 tests cover download, checksums, cache, base/fine-tuned variants and
  malformed manifests/path traversal/download failures. No real S3 claim.
- `docker compose config --quiet` passed.
- Docker Engine 29.6.1 became available during final validation. Runtime image
  `alpha-future-fastapi:model-path` built successfully. Real local model passed
  both HTTP endpoints using TestClient inside the image, UID 10001, network none,
  read-only root, 2 GiB memory limit. Elapsed startup plus requests 59.698 s;
  process peak RSS 929.55 MiB. This is a smoke measurement, not a new benchmark.
- HF-cache container check also passed both endpoints with the same restrictions,
  no token and no network: 28.164 s, process peak RSS 929.02 MiB. This proves a
  prepared HF cache works offline; initial private download still requires access.

## Git handoff

Branch `fast_api`. Final model files are removed from the Git index, retained
unchanged on local disk and ignored under `models/`. LFS attributes and local
standard LFS hooks were removed. Old commits retain their historical LFS pointers
and tokenizer blob; history was not rewritten. Existing clones may use
GIT_LFS_SKIP_PUSH=1 when publishing code to avoid historical LFS uploads.
No model bytes, actual `.env`, tokens, caches or environments are staged.
No GitHub push or external deployment performed. S3 remains a future storage option.
