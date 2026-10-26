#!/usr/bin/env bash
set -eu
demo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
demo_env=${1:-.env}
case "$demo_env" in /*) ;; *) demo_env="$demo_root/$demo_env" ;; esac
umask 077
mkdir -p -- "$(dirname -- "$demo_env")"
if [ ! -f "$demo_env" ]; then cp -- "$demo_root/.env.example" "$demo_env"; fi
while IFS= read -r demo_line || [ -n "$demo_line" ]; do
    demo_line=${demo_line%$'\r'}
    case "$demo_line" in [A-Z]*=*) ;; *) continue ;; esac
    demo_key=${demo_line%%=*}
    if ! grep -q "^${demo_key}=" "$demo_env"; then printf '\n%s\n' "$demo_line" >> "$demo_env"; fi
done < "$demo_root/.env.example"
for demo_key in POSTGRES_ADMIN_PASSWORD DB_MIGRATOR_PASSWORD DB_APP_PASSWORD PGADMIN_DEFAULT_PASSWORD DEMO_PASSWORD DEMO_BANK_PASSWORD RECSYS_API_KEY; do
    demo_count=$(awk -v key="$demo_key" 'index($0,key "=")==1 { n++ } END { print n+0 }' "$demo_env")
    [ "$demo_count" = 1 ] || { printf 'Expected exactly one %s in the environment file.\n' "$demo_key" >&2; exit 1; }
    demo_value=$(awk -v key="$demo_key" 'index($0,key "=")==1 { print substr($0,length(key)+2) }' "$demo_env" | tr -d '\r')
    case "$demo_value" in ''|'""'|"''") demo_generate=yes ;; *) demo_generate=no ;; esac
    if [ "$demo_key" = RECSYS_API_KEY ] && [ "$demo_value" = REPLACE_WITH_RANDOM_SECRET ]; then demo_generate=yes; fi
    if [ "$demo_generate" = yes ]; then
        demo_value=$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')
        demo_temp=$(mktemp "${demo_env}.XXXXXX")
        awk -v key="$demo_key" -v value="$demo_value" 'index($0,key "=")==1 { $0=key "=" value } { print }' "$demo_env" > "$demo_temp"
        mv -- "$demo_temp" "$demo_env"
    fi
done
printf '%s\n' 'Demo environment is ready. Account passwords are in DEMO_PASSWORD and DEMO_BANK_PASSWORD.'
