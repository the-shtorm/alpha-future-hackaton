-- Append-only update of two synthetic catalog cards to the eight-purpose vocabulary.
-- Original versions remain referenced by past applications and recommendation snapshots.
SET search_path TO credit, public;

INSERT INTO credit_product_version (
    id, product_id, version_code, currency, facility_kind, min_amount, max_amount,
    min_term_months, max_term_months, annual_rate_pct, allowed_borrower_kinds,
    allowed_purposes, policy, effective_from
)
SELECT md5(v.product_id::text || ':form-contract-3.0')::uuid,
       v.product_id, 'demo-2026-10-24-form-v3', v.currency, v.facility_kind,
       v.min_amount, v.max_amount, v.min_term_months, v.max_term_months,
       v.annual_rate_pct, v.allowed_borrower_kinds, purposes.values,
       jsonb_set(jsonb_set(v.policy, '{purposes}', purposes.values),
                 '{version}', '"demo-2026-10-24-form-v3"'::jsonb),
       greatest(now(), v.effective_from + interval '1 microsecond')
FROM credit_product_version v
JOIN credit_product p ON p.id=v.product_id
CROSS JOIN LATERAL (
    SELECT jsonb_agg(DISTINCT CASE WHEN value='INVESTMENT' THEN 'DEVELOPMENT' ELSE value END) AS values
    FROM jsonb_array_elements_text(v.allowed_purposes)
) purposes
WHERE p.is_synthetic AND p.provider_code='DEMO_BANK' AND p.code IN ('P10','P15')
  AND v.version_code='demo-2026-10-19-v1'
ON CONFLICT (id) DO NOTHING;
