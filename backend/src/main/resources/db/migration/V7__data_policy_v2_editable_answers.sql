SET search_path TO credit, public;

-- Only editable data is normalized. Submitted revisions, decisions and assessments stay immutable.
-- A legacy false proves zero overdue share. A legacy true does not quantify that share.
UPDATE business_profile
SET profile_data = jsonb_set(profile_data, '{financial,overdue}',
        CASE WHEN profile_data #> '{financial,overdue}' = 'false'::jsonb THEN '0'::jsonb ELSE 'null'::jsonb END)
        || jsonb_build_object('legacy_overdue_boolean', profile_data #> '{financial,overdue}')
WHERE jsonb_typeof(profile_data #> '{financial,overdue}') = 'boolean';

UPDATE preliminary_profile
SET answers = jsonb_set(answers, '{financial,overdue}',
        CASE WHEN answers #> '{financial,overdue}' = 'false'::jsonb THEN '0'::jsonb ELSE 'null'::jsonb END),
    field_sources = jsonb_set(field_sources, '{financial.overdue}',
        coalesce(field_sources -> 'financial.overdue', '{}'::jsonb)
        || jsonb_build_object('value_status', CASE WHEN answers #> '{financial,overdue}' = 'false'::jsonb THEN 'KNOWN' ELSE 'UNKNOWN' END,
                             'legacy_boolean_value', answers #> '{financial,overdue}')),
    selected_product_version_id = NULL,
    form_version = 'preliminary-v2', row_version = row_version + 1
WHERE jsonb_typeof(answers #> '{financial,overdue}') = 'boolean';

UPDATE loan_application
SET draft_answers = jsonb_set(draft_answers, '{financial,overdue}',
        CASE WHEN draft_answers #> '{financial,overdue}' = 'false'::jsonb THEN '0'::jsonb ELSE 'null'::jsonb END),
    draft_field_sources = jsonb_set(draft_field_sources, '{financial.overdue}',
        coalesce(draft_field_sources -> 'financial.overdue', '{}'::jsonb)
        || jsonb_build_object('value_status', CASE WHEN draft_answers #> '{financial,overdue}' = 'false'::jsonb THEN 'KNOWN' ELSE 'UNKNOWN' END,
                             'legacy_boolean_value', draft_answers #> '{financial,overdue}')),
    form_version = 'application-v2', row_version = row_version + 1
WHERE status IN ('DRAFT', 'NEEDS_INFO')
    AND jsonb_typeof(draft_answers #> '{financial,overdue}') = 'boolean';
