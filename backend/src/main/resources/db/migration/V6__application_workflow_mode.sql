SET search_path TO credit, public;

-- Preserve the document requirements and semantics of already created dossiers.
-- The API explicitly selects the workflow for every new application.
ALTER TABLE loan_application ADD COLUMN workflow_mode varchar(20) NOT NULL DEFAULT 'DOCUMENTED'
    CHECK (workflow_mode IN ('SIMPLIFIED','DOCUMENTED'));

CREATE FUNCTION guard_workflow_mode() RETURNS trigger
LANGUAGE plpgsql SET search_path = credit, pg_temp AS $$
BEGIN
    IF NEW.workflow_mode IS DISTINCT FROM OLD.workflow_mode THEN
        RAISE EXCEPTION 'Application workflow mode is fixed at creation' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER guard_workflow_mode BEFORE UPDATE ON loan_application
    FOR EACH ROW EXECUTE FUNCTION guard_workflow_mode();
REVOKE ALL ON FUNCTION guard_workflow_mode() FROM PUBLIC;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'credit_app') THEN
        GRANT EXECUTE ON FUNCTION guard_workflow_mode() TO credit_app;
    END IF;
END; $$;
