SET search_path TO credit, public;

CREATE FUNCTION deny_record_mutation() RETURNS trigger
LANGUAGE plpgsql SET search_path = credit, pg_temp AS $$
BEGIN
    RAISE EXCEPTION 'Append-only record: %', TG_TABLE_NAME USING ERRCODE = '23514';
END;
$$;

DO $$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['credit_product_version','recommendation_run','recommendation_item',
        'application_revision','financial_statement','document_version','document_review','revision_document',
        'consent','consent_revocation','application_check_requirement','check_run','assessment_run',
        'credit_decision','loan_contract','disbursement','application_status_history','audit_event']
    LOOP
        EXECUTE format('CREATE TRIGGER protect_history BEFORE UPDATE OR DELETE ON credit.%I FOR EACH ROW EXECUTE FUNCTION credit.deny_record_mutation()', table_name);
    END LOOP;
END;
$$;

CREATE FUNCTION touch_updated_at() RETURNS trigger
LANGUAGE plpgsql SET search_path = credit, pg_temp AS $$
BEGIN
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$$;
DO $$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['app_user','party','business_profile','preliminary_profile','loan_application','application_document_requirement']
    LOOP
        EXECUTE format('CREATE TRIGGER touch_updated BEFORE UPDATE ON credit.%I FOR EACH ROW EXECUTE FUNCTION credit.touch_updated_at()', table_name);
    END LOOP;
END;
$$;

CREATE FUNCTION assert_document_gate(app_id uuid, gate_name text) RETURNS void
LANGUAGE plpgsql SET search_path = credit, pg_temp AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM application_document_requirement r
        WHERE r.application_id = app_id AND r.required_before = gate_name
          AND CASE WHEN gate_name = 'SUBMISSION'
              THEN r.status NOT IN ('RECEIVED','VERIFYING','VERIFIED','NOT_APPLICABLE','WAIVED')
              ELSE r.status NOT IN ('VERIFIED','NOT_APPLICABLE','WAIVED') END
    ) THEN
        RAISE EXCEPTION 'Document gate incomplete: %', gate_name USING ERRCODE = '23514';
    END IF;
END;
$$;

CREATE FUNCTION assert_check_gate(app_id uuid, rev_id uuid, gate_name text) RETURNS void
LANGUAGE plpgsql SET search_path = credit, pg_temp AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM application_check_requirement r
        WHERE r.application_id = app_id AND r.revision_id = rev_id AND r.required_before = gate_name) THEN
        RAISE EXCEPTION 'Check plan missing: %', gate_name USING ERRCODE = '23514';
    END IF;
    IF EXISTS (
        SELECT 1 FROM application_check_requirement r
        LEFT JOIN LATERAL (
            SELECT c.result FROM check_run c WHERE c.application_id = r.application_id
                AND c.revision_id = r.revision_id AND c.check_code = r.check_code AND c.rule_version = r.rule_version
            ORDER BY c.run_number DESC LIMIT 1
        ) latest ON true
        WHERE r.application_id = app_id AND r.revision_id = rev_id AND r.required_before = gate_name
          AND (latest.result IS NULL OR latest.result NOT IN ('PASS','NOT_APPLICABLE'))
    ) THEN
        RAISE EXCEPTION 'Required checks incomplete: %', gate_name USING ERRCODE = '23514';
    END IF;
END;
$$;

CREATE FUNCTION guard_application() RETURNS trigger
LANGUAGE plpgsql SET search_path = credit, pg_temp AS $$
DECLARE allowed text[];
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'DRAFT' OR NEW.active_revision_id IS NOT NULL THEN
            RAISE EXCEPTION 'Application starts as draft' USING ERRCODE = '23514';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM party WHERE id = NEW.applicant_party_id AND party_kind IN ('IP','LLC')) THEN
            RAISE EXCEPTION 'Borrower must be IP or LLC' USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF ROW(NEW.applicant_party_id, NEW.created_by, NEW.application_number)
        IS DISTINCT FROM ROW(OLD.applicant_party_id, OLD.created_by, OLD.application_number) THEN
        RAISE EXCEPTION 'Application identity is fixed' USING ERRCODE = '23514';
    END IF;
    IF ROW(NEW.draft_answers, NEW.draft_field_sources, NEW.requested_amount, NEW.requested_term_months,
        NEW.product_version_id, NEW.currency, NEW.purpose, NEW.form_version)
        IS DISTINCT FROM ROW(OLD.draft_answers, OLD.draft_field_sources, OLD.requested_amount, OLD.requested_term_months,
            OLD.product_version_id, OLD.currency, OLD.purpose, OLD.form_version)
        AND OLD.status NOT IN ('DRAFT','NEEDS_INFO') THEN
        RAISE EXCEPTION 'Request changes require draft or needs-info state' USING ERRCODE = '23514';
    END IF;
    IF NEW.active_revision_id IS DISTINCT FROM OLD.active_revision_id
        AND OLD.status NOT IN ('DRAFT','NEEDS_INFO') THEN
        RAISE EXCEPTION 'Revision can change only on submission' USING ERRCODE = '23514';
    END IF;
    IF NEW.status = OLD.status THEN RETURN NEW; END IF;
    allowed := CASE OLD.status
        WHEN 'DRAFT' THEN ARRAY['SUBMITTED','CANCELLED']
        WHEN 'SUBMITTED' THEN ARRAY['VALIDATING','NEEDS_INFO','CANCELLED']
        WHEN 'VALIDATING' THEN ARRAY['ENRICHING','NEEDS_INFO','DECLINED','CANCELLED']
        WHEN 'NEEDS_INFO' THEN ARRAY['DRAFT','SUBMITTED','CANCELLED','EXPIRED']
        WHEN 'ENRICHING' THEN ARRAY['COMPLIANCE_REVIEW','LEGAL_REVIEW','SCORING','NEEDS_INFO','DECLINED','CANCELLED']
        WHEN 'COMPLIANCE_REVIEW' THEN ARRAY['ENRICHING','LEGAL_REVIEW','NEEDS_INFO','DECLINED','CANCELLED']
        WHEN 'LEGAL_REVIEW' THEN ARRAY['SCORING','NEEDS_INFO','DECLINED','CANCELLED']
        WHEN 'SCORING' THEN ARRAY['UNDER_REVIEW','NEEDS_INFO','CANCELLED']
        WHEN 'UNDER_REVIEW' THEN ARRAY['APPROVED','APPROVED_CONDITIONAL','COUNTEROFFERED','DECLINED','NEEDS_INFO','CANCELLED']
        WHEN 'APPROVED' THEN ARRAY['OFFER_ACCEPTED','OFFER_DECLINED','EXPIRED','NEEDS_INFO','CANCELLED']
        WHEN 'APPROVED_CONDITIONAL' THEN ARRAY['OFFER_ACCEPTED','OFFER_DECLINED','EXPIRED','NEEDS_INFO','CANCELLED']
        WHEN 'COUNTEROFFERED' THEN ARRAY['OFFER_ACCEPTED','OFFER_DECLINED','EXPIRED','NEEDS_INFO','CANCELLED']
        WHEN 'OFFER_ACCEPTED' THEN ARRAY['SIGNED','EXPIRED','NEEDS_INFO','CANCELLED']
        WHEN 'SIGNED' THEN ARRAY['READY_FOR_DISBURSEMENT']
        WHEN 'READY_FOR_DISBURSEMENT' THEN ARRAY['DISBURSED','SIGNED']
        WHEN 'DISBURSED' THEN ARRAY['SERVICING','CLOSED']
        WHEN 'SERVICING' THEN ARRAY['CLOSED']
        ELSE ARRAY[]::text[] END;
    IF NOT (NEW.status = ANY(allowed)) THEN
        RAISE EXCEPTION 'Invalid state transition: % -> %', OLD.status, NEW.status USING ERRCODE = '23514';
    END IF;
    IF NEW.last_change_reason IS NULL OR length(btrim(NEW.last_change_reason)) = 0 THEN
        RAISE EXCEPTION 'State change reason required' USING ERRCODE = '23514';
    END IF;
    IF NEW.status = 'SUBMITTED' THEN
        IF NEW.active_revision_id IS NULL OR NEW.active_revision_id IS NOT DISTINCT FROM OLD.active_revision_id THEN
            RAISE EXCEPTION 'Submission requires a new immutable revision' USING ERRCODE = '23514';
        END IF;
        PERFORM assert_document_gate(NEW.id, 'SUBMISSION');
        IF NOT EXISTS (SELECT 1 FROM application_revision r WHERE r.id = NEW.active_revision_id
            AND r.application_id = NEW.id AND r.product_version_id = NEW.product_version_id) THEN
            RAISE EXCEPTION 'Submission product version mismatch' USING ERRCODE = '23514'; END IF;
    END IF;
    IF NEW.status IN ('APPROVED','APPROVED_CONDITIONAL','COUNTEROFFERED','DECLINED') AND NOT EXISTS (
        SELECT 1 FROM credit_decision d WHERE d.application_id = NEW.id AND d.revision_id = NEW.active_revision_id
          AND d.decision_kind = CASE NEW.status WHEN 'APPROVED' THEN 'APPROVED' WHEN 'APPROVED_CONDITIONAL' THEN 'CONDITIONAL'
              WHEN 'COUNTEROFFERED' THEN 'COUNTEROFFER' ELSE 'DECLINED' END
          AND d.decision_number = (SELECT max(d2.decision_number) FROM credit_decision d2 WHERE d2.application_id = NEW.id)
    ) THEN RAISE EXCEPTION 'Matching decision missing' USING ERRCODE = '23514'; END IF;
    IF NEW.status IN ('APPROVED','APPROVED_CONDITIONAL','COUNTEROFFERED') THEN
        PERFORM assert_document_gate(NEW.id, 'DECISION');
        PERFORM assert_check_gate(NEW.id, NEW.active_revision_id, 'DECISION');
    END IF;
    IF NEW.status = 'OFFER_ACCEPTED' AND NOT EXISTS (
        SELECT 1 FROM loan_offer o JOIN credit_decision d ON d.id = o.decision_id
        WHERE o.application_id = NEW.id AND o.response = 'ACCEPTED' AND d.revision_id = NEW.active_revision_id
    ) THEN RAISE EXCEPTION 'Accepted current offer missing' USING ERRCODE = '23514'; END IF;
    IF NEW.status = 'SIGNED' THEN
        PERFORM assert_document_gate(NEW.id, 'SIGNING');
        IF NOT EXISTS (SELECT 1 FROM loan_contract WHERE application_id = NEW.id) THEN
            RAISE EXCEPTION 'Signed contract missing' USING ERRCODE = '23514'; END IF;
    END IF;
    IF NEW.status = 'READY_FOR_DISBURSEMENT' THEN
        PERFORM assert_document_gate(NEW.id, 'DISBURSEMENT');
        PERFORM assert_check_gate(NEW.id, NEW.active_revision_id, 'DISBURSEMENT');
    END IF;
    IF NEW.status = 'DISBURSED' AND NOT EXISTS (SELECT 1 FROM disbursement WHERE application_id = NEW.id) THEN
        RAISE EXCEPTION 'Executed disbursement missing' USING ERRCODE = '23514'; END IF;
    IF NEW.status = 'CLOSED' THEN
        PERFORM assert_document_gate(NEW.id, 'CLOSURE');
        PERFORM assert_check_gate(NEW.id, NEW.active_revision_id, 'CLOSURE');
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER guard_application BEFORE INSERT OR UPDATE ON loan_application
    FOR EACH ROW EXECUTE FUNCTION guard_application();

CREATE FUNCTION record_application_history() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = credit, pg_temp AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO application_party(application_id, party_id, roles) VALUES (NEW.id, NEW.applicant_party_id, '["BORROWER"]');
        INSERT INTO application_status_history(application_id, to_status, changed_by, reason)
            VALUES (NEW.id, NEW.status, NEW.created_by, 'Application created');
    ELSIF NEW.status IS DISTINCT FROM OLD.status THEN
        INSERT INTO application_status_history(application_id, revision_id, from_status, to_status, changed_by, reason)
            VALUES (NEW.id, NEW.active_revision_id, OLD.status, NEW.status, NEW.last_changed_by, NEW.last_change_reason);
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER record_application_history AFTER INSERT OR UPDATE ON loan_application
    FOR EACH ROW EXECUTE FUNCTION record_application_history();

CREATE FUNCTION guard_consent_access() RETURNS trigger
LANGUAGE plpgsql SET search_path = credit, pg_temp AS $$
DECLARE granted consent%ROWTYPE;
BEGIN
    IF TG_TABLE_NAME = 'consent_revocation' THEN
        SELECT * INTO STRICT granted FROM consent WHERE id = NEW.consent_id FOR UPDATE;
        IF NEW.revoked_at < granted.granted_at THEN
            RAISE EXCEPTION 'Revocation precedes consent' USING ERRCODE = '23514'; END IF;
        RETURN NEW;
    END IF;
    IF NEW.access_basis = 'CONSENT' THEN
        SELECT * INTO granted FROM consent WHERE id = NEW.consent_id FOR UPDATE;
        IF NOT FOUND OR granted.application_id <> NEW.application_id OR granted.subject_party_id <> NEW.subject_party_id
            OR granted.consent_kind <> NEW.required_consent_kind OR granted.recipient_code <> NEW.recipient_code
            OR granted.granted_at > NEW.requested_at OR granted.valid_until <= NEW.requested_at
            OR granted.valid_until <= clock_timestamp()
            OR EXISTS (SELECT 1 FROM consent_revocation WHERE consent_id = NEW.consent_id) THEN
            RAISE EXCEPTION 'Consent invalid for this request' USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER guard_consent_access BEFORE INSERT ON external_request FOR EACH ROW EXECUTE FUNCTION guard_consent_access();
CREATE TRIGGER guard_revocation BEFORE INSERT ON consent_revocation FOR EACH ROW EXECUTE FUNCTION guard_consent_access();

CREATE FUNCTION guard_credit_decision() RETURNS trigger
LANGUAGE plpgsql SET search_path = credit, pg_temp AS $$
DECLARE app loan_application%ROWTYPE;
BEGIN
    SELECT * INTO STRICT app FROM loan_application WHERE id = NEW.application_id FOR UPDATE;
    IF NEW.revision_id IS DISTINCT FROM app.active_revision_id THEN
        RAISE EXCEPTION 'Decision must use active revision' USING ERRCODE = '23514'; END IF;
    IF NOT EXISTS (SELECT 1 FROM user_role r JOIN app_user u ON u.id = r.user_id
        WHERE r.user_id = NEW.decided_by AND r.role_code = 'BANK_APPROVER' AND u.status = 'ACTIVE') THEN
        RAISE EXCEPTION 'Active bank approver required' USING ERRCODE = '23514'; END IF;
    IF NEW.decision_kind IN ('APPROVED','CONDITIONAL','COUNTEROFFER') THEN
        IF app.status <> 'UNDER_REVIEW' THEN
            RAISE EXCEPTION 'Approval requires under-review state' USING ERRCODE = '23514'; END IF;
        PERFORM assert_document_gate(app.id, 'DECISION');
        PERFORM assert_check_gate(app.id, NEW.revision_id, 'DECISION');
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER guard_credit_decision BEFORE INSERT ON credit_decision FOR EACH ROW EXECUTE FUNCTION guard_credit_decision();

CREATE FUNCTION guard_offer() RETURNS trigger
LANGUAGE plpgsql SET search_path = credit, pg_temp AS $$
DECLARE app loan_application%ROWTYPE;
BEGIN
    SELECT * INTO STRICT app FROM loan_application WHERE id = NEW.application_id FOR UPDATE;
    IF TG_OP = 'UPDATE' THEN
        IF OLD.response IS NOT NULL OR ROW(NEW.id,NEW.application_id,NEW.decision_id,NEW.version_no,NEW.terms,NEW.terms_sha256,NEW.issued_at,NEW.expires_at)
            IS DISTINCT FROM ROW(OLD.id,OLD.application_id,OLD.decision_id,OLD.version_no,OLD.terms,OLD.terms_sha256,OLD.issued_at,OLD.expires_at) THEN
            RAISE EXCEPTION 'Offer terms and final response are immutable' USING ERRCODE = '23514'; END IF;
        IF NEW.response IS NULL THEN RAISE EXCEPTION 'Offer response required' USING ERRCODE = '23514'; END IF;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM credit_decision d WHERE d.id = NEW.decision_id
        AND d.application_id = NEW.application_id AND d.revision_id = app.active_revision_id
        AND d.decision_kind IN ('APPROVED','CONDITIONAL','COUNTEROFFER') AND d.valid_until >= NEW.expires_at
        AND d.decision_number = (SELECT max(d2.decision_number) FROM credit_decision d2 WHERE d2.application_id = app.id)) THEN
        RAISE EXCEPTION 'Current positive decision required for offer' USING ERRCODE = '23514'; END IF;
    IF NEW.response IS NOT NULL AND (NEW.expires_at <= clock_timestamp()
        OR app.status NOT IN ('APPROVED','APPROVED_CONDITIONAL','COUNTEROFFERED')) THEN
        RAISE EXCEPTION 'Offer no longer available for response' USING ERRCODE = '23514'; END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER guard_offer BEFORE INSERT OR UPDATE ON loan_offer FOR EACH ROW EXECUTE FUNCTION guard_offer();

CREATE FUNCTION guard_contract_and_disbursement() RETURNS trigger
LANGUAGE plpgsql SET search_path = credit, pg_temp AS $$
DECLARE app loan_application%ROWTYPE;
BEGIN
    SELECT * INTO STRICT app FROM loan_application WHERE id = NEW.application_id FOR UPDATE;
    IF TG_TABLE_NAME = 'loan_contract' THEN
        IF app.status <> 'OFFER_ACCEPTED' OR NOT EXISTS (
            SELECT 1 FROM loan_offer o JOIN credit_decision d ON d.id = o.decision_id
            WHERE o.id = NEW.offer_id AND o.application_id = app.id AND o.response = 'ACCEPTED'
                AND d.revision_id = app.active_revision_id
        ) THEN RAISE EXCEPTION 'Accepted current offer required for contract' USING ERRCODE = '23514'; END IF;
        IF NOT EXISTS (SELECT 1 FROM document_version WHERE id = NEW.signed_document_version_id
            AND application_id = app.id AND subject_party_id = app.applicant_party_id AND type_code = 'CREDIT_CONTRACT') THEN
            RAISE EXCEPTION 'Borrower credit-contract document required' USING ERRCODE = '23514'; END IF;
        PERFORM assert_document_gate(app.id, 'SIGNING');
    ELSE
        IF app.status <> 'READY_FOR_DISBURSEMENT' THEN
            RAISE EXCEPTION 'Disbursement requires readiness gate' USING ERRCODE = '23514'; END IF;
        PERFORM assert_document_gate(app.id, 'DISBURSEMENT');
        PERFORM assert_check_gate(app.id, app.active_revision_id, 'DISBURSEMENT');
        IF NEW.currency <> app.currency OR NOT EXISTS (
            SELECT 1 FROM loan_contract c JOIN loan_offer o ON o.id = c.offer_id JOIN credit_decision d ON d.id = o.decision_id
            WHERE c.id = NEW.contract_id AND c.application_id = app.id AND NEW.amount <= d.approved_amount
        ) THEN RAISE EXCEPTION 'Invalid disbursement amount or currency' USING ERRCODE = '23514'; END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER guard_contract BEFORE INSERT ON loan_contract FOR EACH ROW EXECUTE FUNCTION guard_contract_and_disbursement();
CREATE TRIGGER guard_disbursement BEFORE INSERT ON disbursement FOR EACH ROW EXECUTE FUNCTION guard_contract_and_disbursement();

CREATE FUNCTION guard_revision_manifest() RETURNS trigger
LANGUAGE plpgsql SET search_path = credit, pg_temp AS $$
DECLARE app loan_application%ROWTYPE;
BEGIN
    SELECT * INTO STRICT app FROM loan_application WHERE id = NEW.application_id FOR UPDATE;
    IF app.status NOT IN ('DRAFT','NEEDS_INFO') THEN
        RAISE EXCEPTION 'Submission snapshot and manifest are already sealed' USING ERRCODE = '23514'; END IF;
    IF TG_TABLE_NAME = 'application_revision' THEN
        IF NEW.product_version_id <> app.product_version_id THEN
            RAISE EXCEPTION 'Snapshot product version mismatch' USING ERRCODE = '23514'; END IF;
    ELSE
        IF EXISTS (SELECT 1 FROM application_status_history h WHERE h.application_id = NEW.application_id
            AND h.revision_id = NEW.revision_id AND h.to_status = 'SUBMITTED') THEN
            RAISE EXCEPTION 'Previously submitted revision remains sealed' USING ERRCODE = '23514'; END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER guard_revision BEFORE INSERT ON application_revision FOR EACH ROW EXECUTE FUNCTION guard_revision_manifest();
CREATE TRIGGER guard_revision_document BEFORE INSERT ON revision_document FOR EACH ROW EXECUTE FUNCTION guard_revision_manifest();
CREATE TRIGGER guard_check_plan BEFORE INSERT ON application_check_requirement FOR EACH ROW EXECUTE FUNCTION guard_revision_manifest();

CREATE FUNCTION guard_external_request_update() RETURNS trigger
LANGUAGE plpgsql SET search_path = credit, pg_temp AS $$
BEGIN
    IF OLD.status <> 'REQUESTED' OR ROW(NEW.id,NEW.application_id,NEW.subject_party_id,NEW.source_code,NEW.purpose,
        NEW.recipient_code,NEW.consent_id,NEW.access_basis,NEW.required_consent_kind,NEW.idempotency_key,NEW.is_simulated,NEW.requested_at)
        IS DISTINCT FROM ROW(OLD.id,OLD.application_id,OLD.subject_party_id,OLD.source_code,OLD.purpose,
            OLD.recipient_code,OLD.consent_id,OLD.access_basis,OLD.required_consent_kind,OLD.idempotency_key,OLD.is_simulated,OLD.requested_at) THEN
        RAISE EXCEPTION 'Request identity and final result are immutable' USING ERRCODE = '23514'; END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER guard_external_request_update BEFORE UPDATE ON external_request FOR EACH ROW EXECUTE FUNCTION guard_external_request_update();
