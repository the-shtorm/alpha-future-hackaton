-- Test-only credentials for an ephemeral PostgreSQL container.
CREATE ROLE credit_migrator LOGIN PASSWORD 'test-migrator';
CREATE ROLE credit_app LOGIN PASSWORD 'test-app';
CREATE SCHEMA credit AUTHORIZATION credit_migrator;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA credit TO credit_app;
