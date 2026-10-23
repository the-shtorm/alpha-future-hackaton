SET search_path TO credit, public;

-- Existing revisions remain immutable; new applications keep their independent selection context.
ALTER TABLE recommendation_run ADD CONSTRAINT uq_recommendation_profile_id UNIQUE (profile_id,id);
ALTER TABLE preliminary_profile ADD COLUMN selected_recommendation_run_id uuid;
ALTER TABLE preliminary_profile ADD CONSTRAINT fk_selected_recommendation
    FOREIGN KEY (id,selected_recommendation_run_id) REFERENCES recommendation_run(profile_id,id);
ALTER TABLE loan_application ADD COLUMN source_profile_version bigint CHECK (source_profile_version>=0);
ALTER TABLE loan_application ADD COLUMN source_preliminary_snapshot jsonb CHECK (jsonb_typeof(source_preliminary_snapshot)='object');

CREATE TABLE macroeconomic_context (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    key_rate_pct numeric(9,5) NOT NULL CHECK (key_rate_pct>=0 AND key_rate_pct<=100),
    valid_from timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    source_code varchar(200) NOT NULL CHECK (length(btrim(source_code))>0),
    recorded_by uuid NOT NULL REFERENCES app_user(id),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CHECK (expires_at>valid_from)
);
CREATE TRIGGER protect_history BEFORE UPDATE OR DELETE ON macroeconomic_context
    FOR EACH ROW EXECUTE FUNCTION deny_record_mutation();

CREATE TABLE counteroffer_proposal (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    decision_id uuid NOT NULL,
    macro_context_id uuid NOT NULL REFERENCES macroeconomic_context(id),
    terms jsonb NOT NULL CHECK (jsonb_typeof(terms)='object'),
    terms_sha256 varchar(64) NOT NULL CHECK (terms_sha256 ~ '^[0-9a-f]{64}$'),
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (application_id,revision_id) REFERENCES application_revision(application_id,id),
    FOREIGN KEY (application_id,decision_id) REFERENCES credit_decision(application_id,id),
    UNIQUE(application_id,decision_id),
    UNIQUE(application_id,id),
    CHECK (expires_at>created_at)
);
CREATE TRIGGER protect_history BEFORE UPDATE OR DELETE ON counteroffer_proposal
    FOR EACH ROW EXECUTE FUNCTION deny_record_mutation();
CREATE TABLE counteroffer_acceptance (
    proposal_id uuid PRIMARY KEY,
    application_id uuid NOT NULL,
    offer_id uuid NOT NULL UNIQUE,
    accepted_by uuid NOT NULL REFERENCES app_user(id),
    terms_sha256 varchar(64) NOT NULL CHECK (terms_sha256 ~ '^[0-9a-f]{64}$'),
    accepted_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (application_id,proposal_id) REFERENCES counteroffer_proposal(application_id,id),
    FOREIGN KEY (application_id,offer_id) REFERENCES loan_offer(application_id,id)
);
CREATE TRIGGER protect_history BEFORE UPDATE OR DELETE ON counteroffer_acceptance
    FOR EACH ROW EXECUTE FUNCTION deny_record_mutation();

DO $$ BEGIN
    IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='credit_app') THEN
        GRANT SELECT,INSERT ON macroeconomic_context,counteroffer_proposal,counteroffer_acceptance TO credit_app;
    END IF;
END; $$;
