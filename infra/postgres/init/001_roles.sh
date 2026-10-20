#!/usr/bin/env bash
set -euo pipefail
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=ON_ERROR_STOP=1 \
  --set=migrator_password="$DB_MIGRATOR_PASSWORD" \
  --set=app_password="$DB_APP_PASSWORD" <<'SQL'
CREATE ROLE credit_migrator LOGIN PASSWORD :'migrator_password';
CREATE ROLE credit_app LOGIN PASSWORD :'app_password';
CREATE SCHEMA credit AUTHORIZATION credit_migrator;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA credit TO credit_app;
SQL

