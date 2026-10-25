# HF/Xet cache on a read-only Docker runtime

User reported health: starting after recreating FastAPI for public HF loading.
Inspection found repeated startup failures: the first HF download attempted Xet
cache/log writes under /app/.cache/huggingface/xet on the read-only root filesystem.
Earlier Linux smoke checks used a prepared cache, so they missed this cold-download
path. The error was reproduced on the user's newly created named cache volume.

Fix in Dockerfile and compose.yaml: direct HF_HOME to /model-cache/hf-home and
HF_XET_CACHE to /model-cache/xet, retaining the snapshot/runtime cache at
/model-cache. Dockerfile defaults also set HF_CACHE_DIR=/model-cache.
All locations share the existing persistent writable model volume. Source choice
still requires only MODEL_PATH; authentication remains optional for public HF.
Non-root UID, read-only root, memory limit, weights and contracts are unchanged.

Validation and rollout completed:

- docker compose config --quiet passed.
- docker compose up -d --build --no-deps fastapi rebuilt the image and recreated
  only FastAPI. Other services and existing volumes were not targeted.
- The real HF transfer completed all ten files in approximately 22 seconds.
  Model initialization completed, readiness returned HTTP 200, and Docker reports
  healthy with RestartCount=0 after two minutes.
- Actual HF constants inside the container resolve HF_HOME=/model-cache/hf-home
  and HF_XET_CACHE=/model-cache/xet; /model-cache is writable for the runtime user.
- Actual HTTP requests to both rank and rank-java returned 200 and all three
  supplied candidates. The checks ran against the working uvicorn process, using
  the internal key inside the container without printing it.
- Live model-info confirms dimension 384, CPU, fine-tuned artifact SHA
  116acca8c00237091e511ea6e96a2959ad1345d9439b8c5a9c7fc2c29b9012e8 and the
  unchanged maximum cosine distance 0.5237781852483749.
- MODEL_PATH points to the pinned hf:// source. Inference uses the loaded model;
  downloaded files and Xet resources now persist in the writable cache volume.
- git diff --check passed. No Python application or contract changes, so the full
  unit suite was not repeated for this configuration-only fix.

The 104-file supporting HF package was refreshed with the fixed Dockerfile:
commit f8c245d1ab7e5cf3576359d957f091b6e2ef8e65. Frozen model files and runtime
model transport revision e93f86ce54f0a6d2b3da24dac803e50ee92bbb2b remain unchanged.
No GitHub push, commit or secret changes. New report outside docs/agents/ because
the user forbids docs edits. Dockerfile and Compose changes remain local.
