SET search_path TO credit, public;

CREATE TABLE loan_application (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    application_number bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    applicant_party_id uuid NOT NULL REFERENCES party(id),
    created_by uuid NOT NULL REFERENCES app_user(id),
    assigned_to uuid REFERENCES app_user(id),
    preliminary_profile_id uuid REFERENCES preliminary_profile(id),
    product_version_id uuid NOT NULL REFERENCES credit_product_version(id),
    requested_amount numeric(19,2) NOT NULL CHECK (requested_amount > 0),
    requested_term_months integer NOT NULL CHECK (requested_term_months > 0),
    currency char(3) NOT NULL DEFAULT 'RUB' CHECK (currency ~ '^[A-Z]{3}$'),
    purpose varchar(80) NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'DRAFT',
    form_version varchar(80) NOT NULL,
    draft_answers jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(draft_answers) = 'object'),
    draft_field_sources jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(draft_field_sources) = 'object'),
    active_revision_id uuid,
    last_changed_by uuid REFERENCES app_user(id),
    last_change_reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    row_version bigint NOT NULL DEFAULT 0,
    CHECK (status IN ('DRAFT','SUBMITTED','VALIDATING','NEEDS_INFO','ENRICHING','COMPLIANCE_REVIEW',
        'LEGAL_REVIEW','SCORING','UNDER_REVIEW','APPROVED','APPROVED_CONDITIONAL','COUNTEROFFERED',
        'DECLINED','OFFER_ACCEPTED','OFFER_DECLINED','EXPIRED','SIGNED','READY_FOR_DISBURSEMENT',
        'DISBURSED','SERVICING','CLOSED','CANCELLED'))
);
CREATE INDEX ix_application_party ON loan_application(applicant_party_id, created_at DESC);
CREATE INDEX ix_application_creator ON loan_application(created_by, created_at DESC);
CREATE INDEX ix_application_work_queue ON loan_application(status, assigned_to, created_at);
CREATE INDEX ix_application_product ON loan_application(product_version_id);

CREATE TABLE application_party (
    application_id uuid NOT NULL REFERENCES loan_application(id),
    party_id uuid NOT NULL REFERENCES party(id),
    roles jsonb NOT NULL CHECK (jsonb_typeof(roles) = 'array' AND jsonb_array_length(roles) > 0),
    details jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(details) = 'object'),
    PRIMARY KEY (application_id, party_id)
);
CREATE INDEX ix_application_party_subject ON application_party(party_id);

CREATE TABLE application_revision (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id uuid NOT NULL REFERENCES loan_application(id),
    revision_no integer NOT NULL CHECK (revision_no > 0),
    submitted_by uuid NOT NULL REFERENCES app_user(id),
    form_version varchar(80) NOT NULL,
    product_version_id uuid NOT NULL REFERENCES credit_product_version(id),
    snapshot jsonb NOT NULL CHECK (jsonb_typeof(snapshot) = 'object'),
    snapshot_sha256 varchar(64) NOT NULL CHECK (snapshot_sha256 ~ '^[0-9a-f]{64}$'),
    submission_evidence jsonb NOT NULL CHECK (jsonb_typeof(submission_evidence) = 'object'),
    submitted_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (application_id, revision_no),
    UNIQUE (application_id, id)
);
ALTER TABLE loan_application ADD CONSTRAINT fk_application_active_revision
    FOREIGN KEY (id, active_revision_id) REFERENCES application_revision(application_id, id)
    DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE financial_statement (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id uuid NOT NULL,
    subject_party_id uuid NOT NULL,
    period_from date NOT NULL,
    period_to date NOT NULL,
    currency char(3) NOT NULL DEFAULT 'RUB' CHECK (currency ~ '^[A-Z]{3}$'),
    revenue numeric(19,2) CHECK (revenue >= 0),
    account_inflow numeric(19,2) CHECK (account_inflow >= 0),
    operating_expenses numeric(19,2) CHECK (operating_expenses >= 0),
    net_profit numeric(19,2),
    debt_balance numeric(19,2) CHECK (debt_balance >= 0),
    monthly_debt_payment numeric(19,2) CHECK (monthly_debt_payment >= 0),
    verification_status varchar(24) NOT NULL CHECK (verification_status IN ('DECLARED','PARTIAL','VERIFIED','DISPUTED')),
    source_details jsonb NOT NULL CHECK (jsonb_typeof(source_details) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (application_id, subject_party_id) REFERENCES application_party(application_id, party_id),
    CHECK (period_to >= period_from)
);
CREATE INDEX ix_financial_application ON financial_statement(application_id, subject_party_id, period_to DESC);

CREATE TABLE document_type (
    code varchar(64) PRIMARY KEY,
    name varchar(250) NOT NULL,
    sensitive boolean NOT NULL DEFAULT true
);

CREATE TABLE document (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id uuid NOT NULL,
    subject_party_id uuid NOT NULL,
    type_code varchar(64) NOT NULL REFERENCES document_type(code),
    title varchar(300) NOT NULL,
    created_by uuid REFERENCES app_user(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (application_id, subject_party_id) REFERENCES application_party(application_id, party_id),
    UNIQUE (id, application_id, subject_party_id, type_code)
);
CREATE INDEX ix_document_application ON document(application_id, type_code);

CREATE TABLE document_version (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id uuid NOT NULL,
    application_id uuid NOT NULL,
    subject_party_id uuid NOT NULL,
    type_code varchar(64) NOT NULL,
    version_no integer NOT NULL CHECK (version_no > 0),
    storage_key varchar(700) NOT NULL UNIQUE,
    original_filename varchar(300) NOT NULL,
    media_type varchar(120) NOT NULL,
    size_bytes bigint NOT NULL CHECK (size_bytes > 0),
    sha256 varchar(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    period_from date,
    period_to date,
    uploaded_by uuid REFERENCES app_user(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (document_id, application_id, subject_party_id, type_code)
        REFERENCES document(id, application_id, subject_party_id, type_code),
    UNIQUE (document_id, version_no),
    UNIQUE (application_id, id),
    UNIQUE (id, application_id, subject_party_id, type_code),
    CHECK (period_to IS NULL OR period_from IS NULL OR period_to >= period_from)
);
CREATE INDEX ix_document_version_application ON document_version(application_id);

CREATE TABLE document_review (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    review_number bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    document_version_id uuid NOT NULL REFERENCES document_version(id),
    review_kind varchar(24) NOT NULL CHECK (review_kind IN ('ANTIVIRUS','FORMAT','SIGNATURE','AUTHENTICITY','CONTENT')),
    result varchar(24) NOT NULL CHECK (result IN ('PASS','FAIL','REVIEW','UNKNOWN','ERROR')),
    reviewer_id uuid REFERENCES app_user(id),
    engine_version varchar(120),
    details jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(details) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_document_review_latest ON document_review(document_version_id, review_kind, created_at DESC);

CREATE TABLE application_document_requirement (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id uuid NOT NULL,
    subject_party_id uuid NOT NULL,
    type_code varchar(64) NOT NULL REFERENCES document_type(code),
    requirement_key varchar(160) NOT NULL,
    basis varchar(20) NOT NULL CHECK (basis IN ('LAW','POLICY','DEMO')),
    reason text NOT NULL,
    policy_version varchar(120) NOT NULL,
    required_before varchar(24) NOT NULL CHECK (required_before IN ('SUBMISSION','DECISION','SIGNING','DISBURSEMENT','SERVICING','CLOSURE')),
    status varchar(24) NOT NULL DEFAULT 'REQUIRED' CHECK (status IN ('NOT_APPLICABLE','REQUIRED','RECEIVED','VERIFYING','VERIFIED','NEEDS_CORRECTION','WAIVED')),
    waiver_reason text,
    due_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    row_version bigint NOT NULL DEFAULT 0,
    FOREIGN KEY (application_id, subject_party_id) REFERENCES application_party(application_id, party_id),
    UNIQUE (application_id, requirement_key),
    UNIQUE (id, application_id, subject_party_id, type_code),
    CHECK (status <> 'WAIVED' OR (basis IN ('POLICY','DEMO') AND length(btrim(waiver_reason)) > 0 AND waiver_reason IS NOT NULL))
);
CREATE INDEX ix_requirements_gate ON application_document_requirement(application_id, required_before, status);

CREATE TABLE requirement_document (
    requirement_id uuid NOT NULL,
    document_version_id uuid NOT NULL,
    application_id uuid NOT NULL,
    subject_party_id uuid NOT NULL,
    type_code varchar(64) NOT NULL,
    PRIMARY KEY (requirement_id, document_version_id),
    FOREIGN KEY (requirement_id, application_id, subject_party_id, type_code)
        REFERENCES application_document_requirement(id, application_id, subject_party_id, type_code),
    FOREIGN KEY (document_version_id, application_id, subject_party_id, type_code)
        REFERENCES document_version(id, application_id, subject_party_id, type_code)
);
CREATE INDEX ix_requirement_document_version ON requirement_document(document_version_id);

CREATE TABLE revision_document (
    application_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    document_version_id uuid NOT NULL,
    PRIMARY KEY (revision_id, document_version_id),
    FOREIGN KEY (application_id, revision_id) REFERENCES application_revision(application_id, id),
    FOREIGN KEY (application_id, document_version_id) REFERENCES document_version(application_id, id)
);
CREATE INDEX ix_revision_document_file ON revision_document(document_version_id);

CREATE TABLE consent (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id uuid NOT NULL,
    subject_party_id uuid NOT NULL,
    consent_kind varchar(32) NOT NULL CHECK (consent_kind IN ('CREDIT_REPORT','PERSONAL_DATA','FINANCIAL_ACCESS','AUTOMATED_DECISION','MARKETING')),
    recipient_code varchar(100) NOT NULL,
    purpose text NOT NULL,
    template_version varchar(100) NOT NULL,
    text_sha256 varchar(64) NOT NULL CHECK (text_sha256 ~ '^[0-9a-f]{64}$'),
    signed_content jsonb NOT NULL CHECK (jsonb_typeof(signed_content) = 'object'),
    signature_evidence jsonb NOT NULL CHECK (jsonb_typeof(signature_evidence) = 'object'),
    recorded_by uuid REFERENCES app_user(id),
    granted_at timestamptz NOT NULL,
    valid_until timestamptz NOT NULL,
    FOREIGN KEY (application_id, subject_party_id) REFERENCES application_party(application_id, party_id),
    UNIQUE (id, application_id, subject_party_id),
    CHECK (valid_until > granted_at)
);
CREATE INDEX ix_consent_subject ON consent(application_id, subject_party_id, consent_kind, valid_until);

CREATE TABLE consent_revocation (
    consent_id uuid PRIMARY KEY REFERENCES consent(id),
    revoked_at timestamptz NOT NULL DEFAULT now(),
    evidence jsonb NOT NULL CHECK (jsonb_typeof(evidence) = 'object')
);

CREATE TABLE external_request (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id uuid NOT NULL,
    subject_party_id uuid NOT NULL,
    source_code varchar(60) NOT NULL,
    purpose text NOT NULL,
    recipient_code varchar(100) NOT NULL DEFAULT 'DEMO_BANK',
    consent_id uuid,
    access_basis varchar(24) NOT NULL CHECK (access_basis IN ('PUBLIC','LAW','CONTRACT','CONSENT')),
    required_consent_kind varchar(32),
    idempotency_key varchar(160) NOT NULL UNIQUE,
    is_simulated boolean NOT NULL DEFAULT true,
    status varchar(24) NOT NULL DEFAULT 'REQUESTED' CHECK (status IN ('REQUESTED','SUCCEEDED','NOT_FOUND','ERROR','CANCELLED')),
    requested_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    response_summary jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(response_summary) = 'object'),
    response_storage_key varchar(700),
    error_code varchar(100),
    FOREIGN KEY (application_id, subject_party_id) REFERENCES application_party(application_id, party_id),
    FOREIGN KEY (consent_id, application_id, subject_party_id) REFERENCES consent(id, application_id, subject_party_id),
    CHECK ((access_basis = 'CONSENT' AND consent_id IS NOT NULL AND required_consent_kind IS NOT NULL)
        OR (access_basis <> 'CONSENT' AND consent_id IS NULL AND required_consent_kind IS NULL)),
    CHECK (source_code <> 'BKI_MAIN_REPORT' OR (access_basis = 'CONSENT' AND required_consent_kind = 'CREDIT_REPORT')),
    CHECK ((status = 'REQUESTED' AND completed_at IS NULL) OR (status <> 'REQUESTED' AND completed_at IS NOT NULL)),
    CHECK (completed_at IS NULL OR completed_at >= requested_at)
);
CREATE INDEX ix_external_application ON external_request(application_id, subject_party_id, source_code);
CREATE INDEX ix_external_pending ON external_request(requested_at) WHERE status = 'REQUESTED';

CREATE TABLE application_check_requirement (
    application_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    check_code varchar(100) NOT NULL,
    rule_version varchar(120) NOT NULL,
    is_legal_gate boolean NOT NULL,
    required_before varchar(24) NOT NULL CHECK (required_before IN ('DECISION','DISBURSEMENT','CLOSURE')),
    reason text NOT NULL,
    PRIMARY KEY (application_id, revision_id, check_code, rule_version),
    FOREIGN KEY (application_id, revision_id) REFERENCES application_revision(application_id, id),
    UNIQUE (application_id, revision_id, check_code, rule_version, is_legal_gate)
);

CREATE TABLE check_run (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_number bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    application_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    check_code varchar(100) NOT NULL,
    rule_version varchar(120) NOT NULL,
    result varchar(24) NOT NULL CHECK (result IN ('PASS','FAIL','REVIEW','UNKNOWN','ERROR','NOT_APPLICABLE')),
    is_legal_gate boolean NOT NULL,
    input_sha256 varchar(64) NOT NULL CHECK (input_sha256 ~ '^[0-9a-f]{64}$'),
    evidence jsonb NOT NULL CHECK (jsonb_typeof(evidence) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (application_id, revision_id, check_code, rule_version, is_legal_gate)
        REFERENCES application_check_requirement(application_id, revision_id, check_code, rule_version, is_legal_gate)
);
CREATE INDEX ix_check_latest ON check_run(application_id, revision_id, check_code, created_at DESC);

CREATE TABLE assessment_run (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    assessment_kind varchar(24) NOT NULL CHECK (assessment_kind IN ('SCORING','FUZZY')),
    model_version varchar(120) NOT NULL,
    feature_version varchar(120) NOT NULL,
    input_sha256 varchar(64) NOT NULL CHECK (input_sha256 ~ '^[0-9a-f]{64}$'),
    input_manifest jsonb NOT NULL CHECK (jsonb_typeof(input_manifest) = 'object'),
    output jsonb NOT NULL CHECK (jsonb_typeof(output) = 'object'),
    is_synthetic boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (application_id, revision_id) REFERENCES application_revision(application_id, id),
    UNIQUE (application_id, revision_id, id)
);
CREATE INDEX ix_assessment_latest ON assessment_run(application_id, revision_id, assessment_kind, created_at DESC);

CREATE TABLE credit_decision (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_number bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    application_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    assessment_id uuid,
    decision_kind varchar(24) NOT NULL CHECK (decision_kind IN ('APPROVED','CONDITIONAL','COUNTEROFFER','DECLINED','REQUEST_INFO')),
    decided_by uuid NOT NULL REFERENCES app_user(id),
    reasoning text NOT NULL CHECK (length(btrim(reasoning)) > 0),
    approved_amount numeric(19,2) CHECK (approved_amount > 0),
    approved_term_months integer CHECK (approved_term_months > 0),
    annual_rate_pct numeric(9,5) CHECK (annual_rate_pct >= 0),
    conditions jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(conditions) = 'object'),
    decided_at timestamptz NOT NULL DEFAULT now(),
    valid_until timestamptz,
    FOREIGN KEY (application_id, revision_id) REFERENCES application_revision(application_id, id),
    FOREIGN KEY (application_id, revision_id, assessment_id) REFERENCES assessment_run(application_id, revision_id, id),
    UNIQUE (application_id, id),
    CHECK (decision_kind NOT IN ('APPROVED','CONDITIONAL','COUNTEROFFER')
        OR (approved_amount IS NOT NULL AND approved_term_months IS NOT NULL AND annual_rate_pct IS NOT NULL AND valid_until IS NOT NULL)),
    CHECK (valid_until IS NULL OR valid_until > decided_at)
);
CREATE INDEX ix_decision_application ON credit_decision(application_id, decided_at DESC);

CREATE TABLE loan_offer (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id uuid NOT NULL,
    decision_id uuid NOT NULL,
    version_no integer NOT NULL CHECK (version_no > 0),
    terms jsonb NOT NULL CHECK (jsonb_typeof(terms) = 'object'),
    terms_sha256 varchar(64) NOT NULL CHECK (terms_sha256 ~ '^[0-9a-f]{64}$'),
    issued_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    response varchar(16) CHECK (response IN ('ACCEPTED','DECLINED')),
    responded_by uuid REFERENCES app_user(id),
    responded_at timestamptz,
    response_evidence jsonb,
    FOREIGN KEY (application_id, decision_id) REFERENCES credit_decision(application_id, id),
    UNIQUE (application_id, version_no),
    UNIQUE (application_id, id),
    CHECK (expires_at > issued_at),
    CHECK ((response IS NULL AND responded_by IS NULL AND responded_at IS NULL AND response_evidence IS NULL)
        OR (response IS NOT NULL AND responded_by IS NOT NULL AND responded_at IS NOT NULL
            AND jsonb_typeof(response_evidence) = 'object' AND response_evidence IS NOT NULL)),
    CHECK (responded_at IS NULL OR (responded_at >= issued_at AND responded_at <= expires_at))
);

CREATE TABLE loan_contract (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id uuid NOT NULL,
    offer_id uuid NOT NULL,
    contract_number varchar(100) NOT NULL UNIQUE,
    signed_document_version_id uuid NOT NULL,
    signed_at timestamptz NOT NULL,
    signature_evidence jsonb NOT NULL CHECK (jsonb_typeof(signature_evidence) = 'object'),
    is_simulated boolean NOT NULL DEFAULT true,
    FOREIGN KEY (application_id, offer_id) REFERENCES loan_offer(application_id, id),
    FOREIGN KEY (application_id, signed_document_version_id) REFERENCES document_version(application_id, id),
    UNIQUE (application_id, id),
    UNIQUE (application_id)
);

CREATE TABLE disbursement (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id uuid NOT NULL,
    contract_id uuid NOT NULL,
    operation_key varchar(160) NOT NULL UNIQUE,
    amount numeric(19,2) NOT NULL CHECK (amount > 0),
    currency char(3) NOT NULL DEFAULT 'RUB' CHECK (currency ~ '^[A-Z]{3}$'),
    executed_at timestamptz NOT NULL DEFAULT now(),
    evidence jsonb NOT NULL CHECK (jsonb_typeof(evidence) = 'object'),
    is_simulated boolean NOT NULL DEFAULT true,
    FOREIGN KEY (application_id, contract_id) REFERENCES loan_contract(application_id, id),
    UNIQUE (application_id)
);
CREATE INDEX ix_disbursement_application ON disbursement(application_id, executed_at);

CREATE TABLE application_status_history (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id uuid NOT NULL REFERENCES loan_application(id),
    revision_id uuid,
    from_status varchar(32),
    to_status varchar(32) NOT NULL,
    changed_by uuid REFERENCES app_user(id),
    reason text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (application_id, revision_id) REFERENCES application_revision(application_id, id)
);
CREATE INDEX ix_status_history_application ON application_status_history(application_id, id);

CREATE TABLE audit_event (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_id uuid REFERENCES app_user(id),
    application_id uuid REFERENCES loan_application(id),
    event_code varchar(100) NOT NULL,
    target_kind varchar(80) NOT NULL,
    target_id uuid,
    metadata jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(metadata) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_audit_application ON audit_event(application_id, id);

CREATE TABLE outbox_event (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id uuid NOT NULL REFERENCES loan_application(id),
    event_type varchar(100) NOT NULL,
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    available_at timestamptz NOT NULL DEFAULT now(),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    processed_at timestamptz,
    last_error_code varchar(120)
);
CREATE INDEX ix_outbox_pending ON outbox_event(available_at, id) WHERE processed_at IS NULL;
