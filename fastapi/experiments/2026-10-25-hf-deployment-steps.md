# HF deployment instructions given to the operator

Request: explain the remaining operator steps to enable HF loading.
Read current Compose, model transport lock, ready healthcheck, Git ignore rules
and official HF token documentation: https://huggingface.co/docs/hub/security-tokens.

The implementation and private thedauns/e5-credit-finetune-v1 repository are ready.
Operator steps: provide an HF token with read access to that private repository,
set MODEL_PATH=thedauns/e5-credit-finetune-v1 and HF_TOKEN in the existing root .env,
then run docker compose up -d --build --no-deps fastapi from the repository root.
Wait for docker compose ps fastapi to show healthy; ready requires model startup.
Preserve the existing API key/database environment settings. The operator inserts
the token directly into the ignored local file; no token was read or displayed.

Compose already forwards MODEL_PATH/HF_TOKEN and mounts recsys_model_cache at
/model-cache. Keep that named volume to retain downloaded assets between container
recreations. Process RAM is repopulated from disk after each process restart.
The short HF name uses the immutable SHA in config/hf-deployment.lock.json.
For a VPS use its own read secret and persistent storage; credentials do not
automatically transfer from the developer machine's HF CLI authentication.

This was an instructional task: no deployment or restart performed, no new
functional tests needed. No code, docs/, draft.ipynb, .env, models or secrets
changed. A new report is outside docs/agents/ because the user forbids docs edits.
No commit or push performed.
