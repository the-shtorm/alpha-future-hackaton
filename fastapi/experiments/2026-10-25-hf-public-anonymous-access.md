# Public HF repository: anonymous access verification

User asked whether public visibility removes the HF token requirement.
Checked current source: HF_TOKEN is optional; an absent value is passed as None
to snapshot_download. Docker has no inherited host HF CLI authentication.

Actual check used HfApi(token=False), hf_hub_download(token=False,
force_download=True) and get_hf_file_metadata(token=False). Results:

- Repository thedauns/e5-credit-finetune-v1 is private=false and gated=false.
- Pinned revision e93f86ce54f0a6d2b3da24dac803e50ee92bbb2b remains available.
- model/finetune-manifest.json downloaded anonymously into a new ignored cache.
- Anonymous metadata request for model/model.safetensors succeeded; size
  470637416 bytes. The full weights were not downloaded again in this check.

Operator can set MODEL_PATH=thedauns/e5-credit-finetune-v1 and HF_TOKEN= in root
.env, then rebuild/recreate FastAPI as previously documented. Internal service
RECSYS_API_KEY remains required and is unrelated to HF authentication. Disk-cache
and RAM behavior remain as verified in the preceding residency task.

Official download/cache reference consulted:
https://huggingface.co/docs/huggingface_hub/guides/download.
No code, .env, secrets, docs/ or working containers changed; nothing pushed or
committed. This new report is outside docs/agents/ due to the user's docs-edit ban.
