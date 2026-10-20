-- Schema is provisioned by infrastructure (or by Flyway in a disposable test database).
SET search_path TO credit, public;

CREATE TABLE app_user (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    login varchar(120) NOT NULL CHECK (login = btrim(login) AND length(login) >= 3),
    password_hash varchar(255) NOT NULL CHECK (password_hash ~ '^\{(bcrypt|argon2)\}.+'),
    display_name varchar(200) NOT NULL,
    email varchar(254),
    phone varchar(32),
    status varchar(20) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','BLOCKED','DISABLED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    row_version bigint NOT NULL DEFAULT 0 CHECK (row_version >= 0)
);
CREATE UNIQUE INDEX ux_app_user_login ON app_user (lower(login));

CREATE TABLE user_role (
    user_id uuid NOT NULL REFERENCES app_user(id),
    role_code varchar(32) NOT NULL CHECK (role_code IN ('CLIENT','BANK_ANALYST','BANK_APPROVER','COMPLIANCE','ADMIN')),
    PRIMARY KEY (user_id, role_code)
);

CREATE TABLE party (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    party_kind varchar(24) NOT NULL CHECK (party_kind IN ('LLC','IP','PERSON')),
    name varchar(500) NOT NULL,
    tax_id varchar(12),
    registration_number varchar(15),
    registered_on date,
    registry_status varchar(40),
    registered_address jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(registered_address) = 'object'),
    sensitive_data_ciphertext bytea,
    encryption_key_id varchar(120),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    row_version bigint NOT NULL DEFAULT 0,
    CHECK (tax_id IS NULL OR (party_kind = 'LLC' AND tax_id ~ '^[0-9]{10}$')
        OR (party_kind IN ('IP','PERSON') AND tax_id ~ '^[0-9]{12}$')),
    CHECK (registration_number IS NULL OR (party_kind = 'LLC' AND registration_number ~ '^[0-9]{13}$')
        OR (party_kind = 'IP' AND registration_number ~ '^[0-9]{15}$')),
    CHECK ((sensitive_data_ciphertext IS NULL) = (encryption_key_id IS NULL))
);
CREATE UNIQUE INDEX ux_party_tax_id ON party (party_kind, tax_id) WHERE tax_id IS NOT NULL;
CREATE UNIQUE INDEX ux_party_registration ON party (registration_number) WHERE registration_number IS NOT NULL;

CREATE TABLE party_membership (
    party_id uuid NOT NULL REFERENCES party(id),
    user_id uuid NOT NULL REFERENCES app_user(id),
    access_role varchar(20) NOT NULL CHECK (access_role IN ('OWNER','EDITOR','VIEWER')),
    granted_by uuid REFERENCES app_user(id),
    granted_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz,
    PRIMARY KEY (party_id, user_id),
    CHECK (revoked_at IS NULL OR revoked_at >= granted_at)
);
CREATE INDEX ix_membership_user ON party_membership (user_id, party_id) WHERE revoked_at IS NULL;

CREATE TABLE party_relation (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    business_party_id uuid NOT NULL REFERENCES party(id),
    related_party_id uuid NOT NULL REFERENCES party(id),
    relation_kind varchar(32) NOT NULL CHECK (relation_kind IN ('DIRECTOR','OWNER','BENEFICIAL_OWNER','REPRESENTATIVE','IP_OWNER','GROUP_MEMBER')),
    ownership_pct numeric(7,4) CHECK (ownership_pct BETWEEN 0 AND 100),
    authority_basis jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(authority_basis) = 'object'),
    valid_from date,
    valid_to date,
    CHECK (business_party_id <> related_party_id),
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from)
);
CREATE INDEX ix_relation_business ON party_relation (business_party_id);
CREATE INDEX ix_relation_related ON party_relation (related_party_id);

CREATE TABLE business_profile (
    party_id uuid PRIMARY KEY REFERENCES party(id),
    tax_regime varchar(20) CHECK (tax_regime IN ('OSNO','USN','PSN','AUSN','NPD','COMBINED','OTHER','UNKNOWN')),
    actual_started_on date,
    actual_regions jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(actual_regions) = 'array'),
    actual_activities jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(actual_activities) = 'array'),
    profile_data jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(profile_data) = 'object'),
    field_sources jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(field_sources) = 'object'),
    updated_at timestamptz NOT NULL DEFAULT now(),
    row_version bigint NOT NULL DEFAULT 0
);

CREATE TABLE preliminary_profile (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_by uuid REFERENCES app_user(id),
    anonymous_token_hash varchar(64) CHECK (anonymous_token_hash ~ '^[0-9a-f]{64}$'),
    party_id uuid REFERENCES party(id),
    form_version varchar(80) NOT NULL,
    answers jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(answers) = 'object'),
    field_sources jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(field_sources) = 'object'),
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    row_version bigint NOT NULL DEFAULT 0,
    CHECK (num_nonnulls(created_by, anonymous_token_hash) = 1)
);
CREATE UNIQUE INDEX ux_preliminary_anonymous ON preliminary_profile(anonymous_token_hash) WHERE anonymous_token_hash IS NOT NULL;
CREATE INDEX ix_preliminary_user ON preliminary_profile(created_by, created_at DESC);

CREATE TABLE credit_product (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code varchar(40) NOT NULL UNIQUE,
    provider_code varchar(80) NOT NULL,
    name varchar(250) NOT NULL,
    is_synthetic boolean NOT NULL DEFAULT true,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE credit_product_version (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id uuid NOT NULL REFERENCES credit_product(id),
    version_code varchar(80) NOT NULL,
    currency char(3) NOT NULL DEFAULT 'RUB' CHECK (currency ~ '^[A-Z]{3}$'),
    facility_kind varchar(32) NOT NULL,
    min_amount numeric(19,2) NOT NULL CHECK (min_amount > 0),
    max_amount numeric(19,2) NOT NULL CHECK (max_amount >= min_amount),
    min_term_months integer NOT NULL CHECK (min_term_months > 0),
    max_term_months integer NOT NULL CHECK (max_term_months >= min_term_months),
    annual_rate_pct numeric(9,5) CHECK (annual_rate_pct >= 0),
    allowed_borrower_kinds jsonb NOT NULL CHECK (jsonb_typeof(allowed_borrower_kinds) = 'array'),
    allowed_purposes jsonb NOT NULL CHECK (jsonb_typeof(allowed_purposes) = 'array'),
    policy jsonb NOT NULL CHECK (jsonb_typeof(policy) = 'object'),
    effective_from timestamptz NOT NULL DEFAULT now(),
    effective_to timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (product_id, version_code),
    CHECK (effective_to IS NULL OR effective_to > effective_from)
);
CREATE INDEX ix_product_versions_catalog ON credit_product_version(product_id, effective_from DESC);

CREATE TABLE recommendation_run (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id uuid NOT NULL REFERENCES preliminary_profile(id),
    profile_snapshot jsonb NOT NULL CHECK (jsonb_typeof(profile_snapshot) = 'object'),
    model_version varchar(120) NOT NULL,
    policy_version varchar(120) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_recommendation_profile ON recommendation_run(profile_id, created_at DESC);

CREATE TABLE recommendation_item (
    run_id uuid NOT NULL REFERENCES recommendation_run(id),
    product_version_id uuid NOT NULL REFERENCES credit_product_version(id),
    rank integer NOT NULL CHECK (rank > 0),
    score numeric(12,8),
    eligibility varchar(24) NOT NULL CHECK (eligibility IN ('ELIGIBLE','CONDITIONAL','INELIGIBLE','UNKNOWN')),
    explanation jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(explanation) = 'object'),
    PRIMARY KEY (run_id, product_version_id),
    UNIQUE (run_id, rank)
);
