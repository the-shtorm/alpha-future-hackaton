#!/usr/bin/env bash
set -eu
demo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
demo_env=${1:-.env}
demo_project=${2:-}
bash "$demo_root/scripts/setup-demo.sh" "$demo_env"
cd -- "$demo_root"
if [ -n "$demo_project" ]; then
    docker compose --env-file "$demo_env" --project-name "$demo_project" up --build --detach --wait --wait-timeout 2400
else
    docker compose --env-file "$demo_env" up --build --detach --wait --wait-timeout 2400
fi
printf '%s\n' 'Demo is ready. Open http://localhost:3000 (or FRONTEND_PORT from your environment file).'
