SET search_path TO credit, public;

ALTER TABLE preliminary_profile ADD COLUMN selected_product_version_id uuid REFERENCES credit_product_version(id);

CREATE TABLE api_session (
    token_hash varchar(64) PRIMARY KEY CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    user_id uuid NOT NULL REFERENCES app_user(id),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_api_session_user ON api_session(user_id, expires_at);

CREATE TABLE api_submission (
    user_id uuid NOT NULL REFERENCES app_user(id),
    idempotency_key varchar(160) NOT NULL,
    application_id uuid NOT NULL REFERENCES loan_application(id),
    expected_version bigint NOT NULL,
    revision_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, idempotency_key),
    FOREIGN KEY (application_id, revision_id) REFERENCES application_revision(application_id, id)
);
CREATE TRIGGER protect_history BEFORE UPDATE OR DELETE ON api_submission
    FOR EACH ROW EXECUTE FUNCTION deny_record_mutation();

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'credit_app') THEN
        GRANT SELECT, INSERT, UPDATE ON api_session TO credit_app;
        GRANT SELECT, INSERT ON api_submission TO credit_app;
    END IF;
END; $$;
