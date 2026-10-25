# syntax=docker/dockerfile:1

FROM python:3.11-slim-bookworm AS base
COPY --from=ghcr.io/astral-sh/uv:0.10.2 /uv /usr/local/bin/uv
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH" \
    TOKENIZERS_PARALLELISM=false \
    OMP_NUM_THREADS=2 \
    MKL_NUM_THREADS=2

RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid 10001 --home-dir /app --no-create-home app \
    && mkdir /model-cache && chown 10001:10001 /model-cache

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --no-cache

COPY --chown=10001:10001 app ./app
COPY --chown=10001:10001 config ./config
COPY --chown=10001:10001 contracts ./contracts
COPY --chown=10001:10001 scripts ./scripts
COPY --chown=10001:10001 examples ./examples
COPY --chown=10001:10001 evaluation ./evaluation

ENV HF_CACHE_DIR=/model-cache \
    HF_HOME=/model-cache/hf-home \
    HF_XET_CACHE=/model-cache/xet

FROM base AS test
RUN uv sync --frozen --no-install-project --no-cache
COPY tests ./tests
CMD ["python", "-m", "pytest"]

FROM base AS runtime
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=90s --retries=3 \
    CMD ["python", "-m", "app.healthcheck"]
CMD ["python", "-m", "app.server"]
