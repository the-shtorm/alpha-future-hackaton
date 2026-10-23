SET search_path TO credit, public;
CREATE TABLE application_financial_evidence (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id uuid NOT NULL REFERENCES loan_application(id),
    period_from date NOT NULL,
    period_to date NOT NULL CHECK(period_to>=period_from),
    revenue numeric(19,2) NOT NULL CHECK(revenue>=0),
    operations jsonb NOT NULL CHECK(jsonb_typeof(operations)='array'),
    calculation_version varchar(80) NOT NULL,
    submitted_by uuid NOT NULL REFERENCES app_user(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(application_id,id)
);
CREATE TABLE financial_evidence_review (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    evidence_id uuid NOT NULL REFERENCES application_financial_evidence(id),
    result varchar(12) NOT NULL CHECK(result IN ('PASS','FAIL','UNKNOWN')),
    reason varchar(2000) NOT NULL CHECK(length(btrim(reason))>0),
    reviewed_by uuid NOT NULL REFERENCES app_user(id),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER protect_history BEFORE UPDATE OR DELETE ON application_financial_evidence
    FOR EACH ROW EXECUTE FUNCTION deny_record_mutation();
CREATE TRIGGER protect_history BEFORE UPDATE OR DELETE ON financial_evidence_review
    FOR EACH ROW EXECUTE FUNCTION deny_record_mutation();
CREATE INDEX ix_financial_evidence_app ON application_financial_evidence(application_id,created_at DESC,id);
CREATE INDEX ix_financial_evidence_review ON financial_evidence_review(evidence_id,id DESC);
CREATE FUNCTION guard_preliminary_context() RETURNS trigger
LANGUAGE plpgsql SET search_path=credit,pg_temp AS $$ BEGIN
    IF ROW(NEW.preliminary_profile_id,NEW.source_profile_version,NEW.source_preliminary_snapshot)
       IS DISTINCT FROM ROW(OLD.preliminary_profile_id,OLD.source_profile_version,OLD.source_preliminary_snapshot)
       AND OLD.status NOT IN ('DRAFT','NEEDS_INFO') THEN
        RAISE EXCEPTION 'Selection context is sealed' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END; $$;
CREATE TRIGGER guard_preliminary_context BEFORE UPDATE ON loan_application
    FOR EACH ROW EXECUTE FUNCTION guard_preliminary_context();
REVOKE ALL ON FUNCTION guard_preliminary_context() FROM PUBLIC;
DO $$ BEGIN
    IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='credit_app') THEN
        GRANT SELECT,INSERT ON application_financial_evidence,financial_evidence_review TO credit_app;
        GRANT USAGE,SELECT ON SEQUENCE financial_evidence_review_id_seq TO credit_app;
        GRANT EXECUTE ON FUNCTION guard_preliminary_context() TO credit_app;
    END IF;
END; $$;
