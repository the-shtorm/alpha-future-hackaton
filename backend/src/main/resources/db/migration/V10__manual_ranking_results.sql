SET search_path TO credit, public;
-- Only current editable forms are normalized. Historical snapshots are not rewritten.
UPDATE preliminary_profile
SET answers=jsonb_set(answers,'{security,collateralReady}',
        CASE answers#>>'{security,collateralReady}' WHEN 'true' THEN '"YES"'::jsonb ELSE '"NO"'::jsonb END),
    row_version=row_version+1,selected_product_version_id=NULL,selected_recommendation_run_id=NULL,
    form_version='preliminary-1.1'
WHERE jsonb_typeof(answers#>'{security,collateralReady}')='boolean';
UPDATE preliminary_profile
SET answers=jsonb_set(answers,'{security,guarantorReady}',
        CASE answers#>>'{security,guarantorReady}' WHEN 'true' THEN '"YES"'::jsonb ELSE '"NO"'::jsonb END),
    row_version=row_version+1,selected_product_version_id=NULL,selected_recommendation_run_id=NULL,
    form_version='preliminary-1.1'
WHERE jsonb_typeof(answers#>'{security,guarantorReady}')='boolean';
CREATE TABLE manual_ranking_result (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL UNIQUE REFERENCES recommendation_run(id),
    response jsonb NOT NULL CHECK(jsonb_typeof(response)='object'),
    imported_by uuid NOT NULL REFERENCES app_user(id),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER protect_history BEFORE UPDATE OR DELETE ON manual_ranking_result
    FOR EACH ROW EXECUTE FUNCTION deny_record_mutation();
DO $$ BEGIN
    IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='credit_app') THEN
        GRANT SELECT,INSERT ON manual_ranking_result TO credit_app;
    END IF;
END; $$;
