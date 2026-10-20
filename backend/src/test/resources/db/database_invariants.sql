-- Execute only against a disposable database. All fixtures are rolled back.
BEGIN;
SET LOCAL search_path TO credit, public;
SET CONSTRAINTS ALL IMMEDIATE;

CREATE FUNCTION pg_temp.expect_sqlstate(statement_text text, expected_state text) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE actual_state text;
BEGIN
    BEGIN
        EXECUTE statement_text;
    EXCEPTION WHEN OTHERS THEN
        GET STACKED DIAGNOSTICS actual_state = RETURNED_SQLSTATE;
        IF actual_state = expected_state THEN RETURN; END IF;
        RAISE EXCEPTION 'Expected %, got % for %: %', expected_state, actual_state, statement_text, SQLERRM;
    END;
    RAISE EXCEPTION 'Expected SQLSTATE %, but query succeeded: %', expected_state, statement_text;
END;
$$;

DO $$
DECLARE
    client_id uuid := gen_random_uuid(); approver_id uuid := gen_random_uuid();
    borrower_id uuid := gen_random_uuid(); other_party_id uuid := gen_random_uuid(); person_id uuid := gen_random_uuid();
    product_id uuid := gen_random_uuid(); product_version_id uuid := gen_random_uuid();
    app_id uuid := gen_random_uuid(); other_app_id uuid := gen_random_uuid();
    revision_id uuid := gen_random_uuid(); other_revision_id uuid := gen_random_uuid();
    doc_id uuid := gen_random_uuid(); doc_version_id uuid := gen_random_uuid(); requirement_id uuid := gen_random_uuid();
    consent_id uuid := gen_random_uuid(); expired_consent_id uuid := gen_random_uuid(); revoked_consent_id uuid := gen_random_uuid();
    decision_id uuid := gen_random_uuid(); offer_id uuid := gen_random_uuid(); contract_id uuid := gen_random_uuid();
    digest text := repeat('a',64);
    decision_sql text;
BEGIN
    INSERT INTO app_user(id,login,password_hash,display_name) VALUES
        (client_id,'test-client','{bcrypt}$2a$10$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWy','Test client'),
        (approver_id,'test-approver','{bcrypt}$2a$10$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWy','Test approver');
    INSERT INTO user_role VALUES (client_id,'CLIENT'),(approver_id,'BANK_APPROVER');
    INSERT INTO party(id,party_kind,name,tax_id) VALUES
        (borrower_id,'LLC','Synthetic borrower','0000000001'),
        (other_party_id,'LLC','Synthetic other company','0000000002'),
        (person_id,'PERSON','Synthetic person','000000000001');
    INSERT INTO party_membership(party_id,user_id,access_role) VALUES (borrower_id,client_id,'OWNER');
    INSERT INTO credit_product(id,code,provider_code,name) VALUES (product_id,'TEST_ONLY','DEMO_BANK','Invariant fixture');
    INSERT INTO credit_product_version(id,product_id,version_code,facility_kind,min_amount,max_amount,
        min_term_months,max_term_months,allowed_borrower_kinds,allowed_purposes,policy)
        VALUES (product_version_id,product_id,'test-v1','TERM',1000,1000000,1,24,'["LLC"]','["WORKING_CAPITAL"]','{}');

    -- CASE 01: login uniqueness is case-insensitive.
    PERFORM pg_temp.expect_sqlstate(format('INSERT INTO app_user(login,password_hash,display_name) VALUES (%L,%L,%L)',
        'TEST-CLIENT','{bcrypt}placeholder','Duplicate'), '23505');
    -- CASE 02: plaintext passwords are rejected.
    PERFORM pg_temp.expect_sqlstate('INSERT INTO app_user(login,password_hash,display_name) VALUES (''plaintext'',''password'',''Bad'')','23514');
    -- CASE 03: wrong tax-ID shape is rejected.
    PERFORM pg_temp.expect_sqlstate('INSERT INTO party(party_kind,name,tax_id) VALUES (''LLC'',''Bad'',''123'')','23514');
    -- CASE 04: immutable catalog versions cannot be overwritten.
    PERFORM pg_temp.expect_sqlstate(format('UPDATE credit_product_version SET min_amount=2000 WHERE id=%L',product_version_id),'23514');

    INSERT INTO loan_application(id,applicant_party_id,created_by,product_version_id,requested_amount,requested_term_months,purpose,form_version)
        VALUES (app_id,borrower_id,client_id,product_version_id,100000,12,'WORKING_CAPITAL','test-v1'),
               (other_app_id,other_party_id,client_id,product_version_id,100000,12,'WORKING_CAPITAL','test-v1');
    -- CASE 05: business products cannot use an ordinary natural person as borrower.
    PERFORM pg_temp.expect_sqlstate(format('INSERT INTO loan_application(applicant_party_id,created_by,product_version_id,requested_amount,requested_term_months,purpose,form_version) VALUES (%L,%L,%L,1000,12,''X'',''v1'')',person_id,client_id,product_version_id),'23514');
    -- CASE 06: workflow cannot jump from draft to disbursed.
    PERFORM pg_temp.expect_sqlstate(format('UPDATE loan_application SET status=''DISBURSED'',last_change_reason=''Bad'' WHERE id=%L',app_id),'23514');
    -- CASE 07: submission requires an immutable revision.
    PERFORM pg_temp.expect_sqlstate(format('UPDATE loan_application SET status=''SUBMITTED'',last_change_reason=''Submit'' WHERE id=%L',app_id),'23514');

    INSERT INTO application_revision(id,application_id,revision_no,submitted_by,form_version,product_version_id,snapshot,snapshot_sha256,submission_evidence)
        VALUES (revision_id,app_id,1,client_id,'test-v1',product_version_id,'{"request":{"amount":100000},"answers":{}}',digest,'{"simulated":true}'),
               (other_revision_id,other_app_id,1,client_id,'test-v1',product_version_id,'{}',digest,'{"simulated":true}');
    -- CASE 08: current revision cannot belong to another application.
    PERFORM pg_temp.expect_sqlstate(format('UPDATE loan_application SET active_revision_id=%L WHERE id=%L',other_revision_id,app_id),'23503');
    -- CASE 09: submitted snapshot contents cannot be edited.
    PERFORM pg_temp.expect_sqlstate(format('UPDATE application_revision SET snapshot=''{}'' WHERE id=%L',revision_id),'23514');

    INSERT INTO document(id,application_id,subject_party_id,type_code,title) VALUES (doc_id,app_id,borrower_id,'BANK_STATEMENT','Fixture statement');
    INSERT INTO document_version(id,document_id,application_id,subject_party_id,type_code,version_no,storage_key,original_filename,media_type,size_bytes,sha256)
        VALUES (doc_version_id,doc_id,app_id,borrower_id,'BANK_STATEMENT',1,'test/statement.pdf','statement.pdf','application/pdf',100,digest);
    INSERT INTO application_document_requirement(id,application_id,subject_party_id,type_code,requirement_key,basis,reason,policy_version,required_before)
        VALUES (requirement_id,other_app_id,other_party_id,'BANK_STATEMENT','statement','POLICY','Test','v1','DECISION');
    -- CASE 10: a document cannot fulfill another company's requirement.
    PERFORM pg_temp.expect_sqlstate(format('INSERT INTO requirement_document VALUES (%L,%L,%L,%L,''BANK_STATEMENT'')',requirement_id,doc_version_id,other_app_id,other_party_id),'23503');
    -- CASE 11: document bytes and hash are versioned rather than replaced.
    PERFORM pg_temp.expect_sqlstate(format('UPDATE document_version SET storage_key=''replaced.pdf'' WHERE id=%L',doc_version_id),'23514');
    -- CASE 12: legal requirements cannot be waived as a policy exception.
    PERFORM pg_temp.expect_sqlstate(format('INSERT INTO application_document_requirement(application_id,subject_party_id,type_code,requirement_key,basis,reason,policy_version,required_before,status,waiver_reason) VALUES (%L,%L,''IDENTITY'',''bad-waiver'',''LAW'',''Test'',''v1'',''DECISION'',''WAIVED'',''High score'')',app_id,borrower_id),'23514');

    INSERT INTO consent(id,application_id,subject_party_id,consent_kind,recipient_code,purpose,template_version,text_sha256,signed_content,signature_evidence,granted_at,valid_until)
        VALUES (consent_id,app_id,borrower_id,'CREDIT_REPORT','DEMO_BANK','Business credit','v1',digest,'{}','{"simulated":true}',now()-interval '1 day',now()+interval '1 day'),
               (expired_consent_id,app_id,borrower_id,'CREDIT_REPORT','DEMO_BANK','Business credit','v1',digest,'{}','{"simulated":true}',now()-interval '2 day',now()-interval '1 day'),
               (revoked_consent_id,app_id,borrower_id,'CREDIT_REPORT','DEMO_BANK','Business credit','v1',digest,'{}','{"simulated":true}',now()-interval '1 day',now()+interval '1 day');
    INSERT INTO consent_revocation(consent_id,evidence) VALUES (revoked_consent_id,'{"simulated":true}');
    -- CASE 13: expired consent cannot authorize a main credit report.
    PERFORM pg_temp.expect_sqlstate(format('INSERT INTO external_request(application_id,subject_party_id,source_code,purpose,consent_id,access_basis,required_consent_kind,idempotency_key) VALUES (%L,%L,''BKI_MAIN_REPORT'',''Test'',%L,''CONSENT'',''CREDIT_REPORT'',''expired'')',app_id,borrower_id,expired_consent_id),'23514');
    -- CASE 14: revoked consent cannot authorize a main credit report.
    PERFORM pg_temp.expect_sqlstate(format('INSERT INTO external_request(application_id,subject_party_id,source_code,purpose,consent_id,access_basis,required_consent_kind,idempotency_key) VALUES (%L,%L,''BKI_MAIN_REPORT'',''Test'',%L,''CONSENT'',''CREDIT_REPORT'',''revoked'')',app_id,borrower_id,revoked_consent_id),'23514');
    -- CASE 15: another subject's consent cannot authorize the request.
    PERFORM pg_temp.expect_sqlstate(format('INSERT INTO external_request(application_id,subject_party_id,source_code,purpose,consent_id,access_basis,required_consent_kind,idempotency_key) VALUES (%L,%L,''BKI_MAIN_REPORT'',''Test'',%L,''CONSENT'',''CREDIT_REPORT'',''wrong-subject'')',other_app_id,other_party_id,consent_id),'23514');
    -- CASE 16: main report cannot be treated as public data.
    PERFORM pg_temp.expect_sqlstate(format('INSERT INTO external_request(application_id,subject_party_id,source_code,purpose,access_basis,idempotency_key) VALUES (%L,%L,''BKI_MAIN_REPORT'',''Test'',''PUBLIC'',''public-report'')',app_id,borrower_id),'23514');
    INSERT INTO external_request(application_id,subject_party_id,source_code,purpose,consent_id,access_basis,required_consent_kind,idempotency_key)
        VALUES (app_id,borrower_id,'BKI_MAIN_REPORT','Business credit',consent_id,'CONSENT','CREDIT_REPORT','valid-report');
    -- CASE 17: request consent and subject are fixed after dispatch registration.
    PERFORM pg_temp.expect_sqlstate('UPDATE external_request SET consent_id=NULL WHERE idempotency_key=''valid-report''','23514');

    INSERT INTO application_check_requirement(application_id,revision_id,check_code,rule_version,is_legal_gate,required_before,reason) VALUES
        (app_id,revision_id,'KYC','v1',true,'DECISION','Test identity gate'),
        (app_id,revision_id,'FINANCIAL','v1',false,'DECISION','Test financial gate'),
        (app_id,revision_id,'RELEASE_READY','v1',true,'DISBURSEMENT','Test release gate'),
        (app_id,revision_id,'PAYOFF_AND_RELEASE','v1',true,'CLOSURE','Test closure gate');
    UPDATE loan_application SET active_revision_id=revision_id,status='SUBMITTED',last_change_reason='Submit',last_changed_by=client_id WHERE id=app_id;
    UPDATE loan_application SET status='VALIDATING',last_change_reason='Validate' WHERE id=app_id;
    UPDATE loan_application SET status='ENRICHING',last_change_reason='Enrich' WHERE id=app_id;
    UPDATE loan_application SET status='SCORING',last_change_reason='Score' WHERE id=app_id;
    UPDATE loan_application SET status='UNDER_REVIEW',last_change_reason='Review' WHERE id=app_id;
    -- CASE 18: no additions to a sealed snapshot's document manifest.
    PERFORM pg_temp.expect_sqlstate(format('INSERT INTO revision_document VALUES (%L,%L,%L)',app_id,revision_id,doc_version_id),'23514');
    -- CASE 19: approval cannot be manufactured by changing a status.
    PERFORM pg_temp.expect_sqlstate(format('UPDATE loan_application SET status=''APPROVED'',last_change_reason=''Fake'' WHERE id=%L',app_id),'23514');
    decision_sql := format('INSERT INTO credit_decision(id,application_id,revision_id,decision_kind,decided_by,reasoning,approved_amount,approved_term_months,annual_rate_pct,valid_until) VALUES (%L,%L,%L,''APPROVED'',%L,''Test'',100000,12,25,now()+interval ''7 days'')',decision_id,app_id,revision_id,approver_id);
    -- CASE 20: missing check results are not PASS.
    PERFORM pg_temp.expect_sqlstate(decision_sql,'23514');
    INSERT INTO check_run(application_id,revision_id,check_code,rule_version,result,is_legal_gate,input_sha256,evidence)
        VALUES (app_id,revision_id,'KYC','v1','PASS',true,digest,'{}'),
               (app_id,revision_id,'FINANCIAL','v1','UNKNOWN',false,digest,'{}');
    -- CASE 21: UNKNOWN blocks approval.
    PERFORM pg_temp.expect_sqlstate(decision_sql,'23514');
    INSERT INTO check_run(application_id,revision_id,check_code,rule_version,result,is_legal_gate,input_sha256,evidence)
        VALUES (app_id,revision_id,'FINANCIAL','v1','PASS',false,digest,'{}'),
               (app_id,revision_id,'FINANCIAL','v1','FAIL',false,digest,'{}');
    -- CASE 22: a later failure takes precedence even within the same transaction timestamp.
    PERFORM pg_temp.expect_sqlstate(decision_sql,'23514');
    INSERT INTO check_run(application_id,revision_id,check_code,rule_version,result,is_legal_gate,input_sha256,evidence)
        VALUES (app_id,revision_id,'FINANCIAL','v1','PASS',false,digest,'{}');
    -- CASE 23: client account cannot impersonate a bank approver.
    PERFORM pg_temp.expect_sqlstate(format('INSERT INTO credit_decision(application_id,revision_id,decision_kind,decided_by,reasoning) VALUES (%L,%L,''DECLINED'',%L,''Test'')',app_id,revision_id,client_id),'23514');
    -- CASE 24: decision cannot point to a different application's revision.
    PERFORM pg_temp.expect_sqlstate(format('INSERT INTO credit_decision(application_id,revision_id,decision_kind,decided_by,reasoning) VALUES (%L,%L,''DECLINED'',%L,''Test'')',app_id,other_revision_id,approver_id),'23514');
    EXECUTE decision_sql;
    UPDATE loan_application SET status='APPROVED',last_change_reason='Approved',last_changed_by=approver_id WHERE id=app_id;
    INSERT INTO loan_offer(id,application_id,decision_id,version_no,terms,terms_sha256,expires_at)
        VALUES (offer_id,app_id,decision_id,1,'{"amount":100000,"term_months":12,"annual_rate_pct":25}',digest,now()+interval '1 day');
    -- CASE 25: published terms cannot be silently edited.
    PERFORM pg_temp.expect_sqlstate(format('UPDATE loan_offer SET terms=''{}'' WHERE id=%L',offer_id),'23514');
    UPDATE loan_offer SET response='ACCEPTED',responded_by=client_id,responded_at=now(),response_evidence='{"simulated":true}' WHERE id=offer_id;
    UPDATE loan_application SET status='OFFER_ACCEPTED',last_change_reason='Accepted',last_changed_by=client_id WHERE id=app_id;
    INSERT INTO document(id,application_id,subject_party_id,type_code,title) VALUES (contract_id,app_id,borrower_id,'CREDIT_CONTRACT','Simulated contract');
    INSERT INTO document_version(id,document_id,application_id,subject_party_id,type_code,version_no,storage_key,original_filename,media_type,size_bytes,sha256)
        VALUES (contract_id,contract_id,app_id,borrower_id,'CREDIT_CONTRACT',1,'test/contract.pdf','contract.pdf','application/pdf',100,digest);
    INSERT INTO loan_contract(id,application_id,offer_id,contract_number,signed_document_version_id,signed_at,signature_evidence)
        VALUES (contract_id,app_id,offer_id,'TEST-CONTRACT',contract_id,now(),'{"simulated":true}');
    UPDATE loan_application SET status='SIGNED',last_change_reason='Simulated signatures' WHERE id=app_id;
    -- CASE 26: unsigned or incomplete readiness checks prevent release.
    PERFORM pg_temp.expect_sqlstate(format('UPDATE loan_application SET status=''READY_FOR_DISBURSEMENT'',last_change_reason=''Release'' WHERE id=%L',app_id),'23514');
    INSERT INTO check_run(application_id,revision_id,check_code,rule_version,result,is_legal_gate,input_sha256,evidence)
        VALUES (app_id,revision_id,'RELEASE_READY','v1','PASS',true,digest,'{"simulated":true}');
    UPDATE loan_application SET status='READY_FOR_DISBURSEMENT',last_change_reason='All demo release checks passed' WHERE id=app_id;
    -- CASE 27: release cannot exceed the approved amount.
    PERFORM pg_temp.expect_sqlstate(format('INSERT INTO disbursement(application_id,contract_id,operation_key,amount,evidence) VALUES (%L,%L,''too-much'',100001,''{}'')',app_id,contract_id),'23514');
    INSERT INTO disbursement(application_id,contract_id,operation_key,amount,evidence) VALUES (app_id,contract_id,'first-draw',100000,'{"simulated":true}');
    -- CASE 28: duplicate operation is not a second disbursement.
    PERFORM pg_temp.expect_sqlstate(format('INSERT INTO disbursement(application_id,contract_id,operation_key,amount,evidence) VALUES (%L,%L,''first-draw'',100000,''{}'')',app_id,contract_id),'23505');
    UPDATE loan_application SET status='DISBURSED',last_change_reason='Simulated first draw' WHERE id=app_id;
    UPDATE loan_application SET status='SERVICING',last_change_reason='Demo servicing' WHERE id=app_id;
    -- CASE 29: closure requires verified payoff/release, not just a UI status.
    PERFORM pg_temp.expect_sqlstate(format('UPDATE loan_application SET status=''CLOSED'',last_change_reason=''Close'' WHERE id=%L',app_id),'23514');
    INSERT INTO check_run(application_id,revision_id,check_code,rule_version,result,is_legal_gate,input_sha256,evidence)
        VALUES (app_id,revision_id,'PAYOFF_AND_RELEASE','v1','PASS',true,digest,'{"simulated":true}');
    UPDATE loan_application SET status='CLOSED',last_change_reason='Demo payoff and release verified' WHERE id=app_id;
    -- CASE 30: history is append-only.
    PERFORM pg_temp.expect_sqlstate(format('DELETE FROM application_status_history WHERE application_id=%L',app_id),'23514');
    UPDATE loan_application SET active_revision_id=other_revision_id,status='SUBMITTED',last_change_reason='Other submit' WHERE id=other_app_id;
    UPDATE loan_application SET status='VALIDATING',last_change_reason='Other validate' WHERE id=other_app_id;
    UPDATE loan_application SET status='NEEDS_INFO',last_change_reason='Other missing info' WHERE id=other_app_id;
    -- CASE 31: needs-info does not reopen the old submitted manifest for insertion.
    PERFORM pg_temp.expect_sqlstate(format('INSERT INTO revision_document VALUES (%L,%L,%L)',other_app_id,other_revision_id,doc_version_id),'23514');
    -- CASE 32: needs-info does not reopen the old check plan either.
    PERFORM pg_temp.expect_sqlstate(format('INSERT INTO application_check_requirement(application_id,revision_id,check_code,rule_version,is_legal_gate,required_before,reason) VALUES (%L,%L,''LATE'',''v1'',true,''DECISION'',''Late injection'')',other_app_id,other_revision_id),'23514');
    IF (SELECT count(*) FROM application_status_history WHERE application_id=app_id) <> 13 THEN
        RAISE EXCEPTION 'Expected 13 state-history entries';
    END IF;
    IF (SELECT status FROM loan_application WHERE id=app_id) <> 'CLOSED' THEN
        RAISE EXCEPTION 'Positive lifecycle did not close';
    END IF;
    RAISE NOTICE 'PASS: 32 negative integrity cases and full simulated lifecycle';
END;
$$;
ROLLBACK;
