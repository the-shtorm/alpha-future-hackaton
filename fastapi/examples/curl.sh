#!/usr/bin/env sh
set -eu
: "${ML_INTERNAL_API_KEY:?Set ML_INTERNAL_API_KEY}"
curl --fail-with-body --max-time 60 \
  -H "Content-Type: application/json" \
  -H "X-Internal-API-Key: ${ML_INTERNAL_API_KEY}" \
  --data-binary @examples/rank-request.json \
  "${ML_BASE_URL:-http://localhost:8000}/api/v1/recommendations/rank"
