SET search_path TO credit, public;
CREATE TABLE recommendation_attempt (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES recommendation_run(id),
    status varchar(32) NOT NULL CHECK(status IN ('READY','EMPTY','NOT_CONFIGURED','UNAVAILABLE','INVALID_RESPONSE')),
    requested_by uuid NOT NULL REFERENCES app_user(id),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_recommendation_attempt_run ON recommendation_attempt(run_id,created_at DESC,id DESC);
CREATE TRIGGER protect_history BEFORE UPDATE OR DELETE ON recommendation_attempt
    FOR EACH ROW EXECUTE FUNCTION deny_record_mutation();
DO $$ BEGIN
    IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='credit_app') THEN
        GRANT SELECT,INSERT ON recommendation_attempt TO credit_app;
        GRANT USAGE,SELECT ON SEQUENCE recommendation_attempt_id_seq TO credit_app;
    END IF;
END; $$;
