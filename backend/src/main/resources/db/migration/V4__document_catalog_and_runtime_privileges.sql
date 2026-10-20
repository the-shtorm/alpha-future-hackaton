SET search_path TO credit, public;

INSERT INTO document_type(code, name, sensitive) VALUES
('IDENTITY','Документ, удостоверяющий личность',true),
('REGISTRY_EXTRACT','Выписка или сведения ЕГРЮЛ/ЕГРИП',false),
('CHARTER','Устав или сведения о типовом уставе',true),
('DIRECTOR_APPOINTMENT','Подтверждение назначения руководителя',true),
('POWER_OF_ATTORNEY','Доверенность и подтверждение полномочий',true),
('OWNERSHIP_STRUCTURE','Структура владения и бенефициары',true),
('CORPORATE_APPROVAL','Применимое корпоративное решение',true),
('BALANCE_SHEET','Бухгалтерский баланс',true),
('INCOME_STATEMENT','Отчет о финансовых результатах',true),
('TAX_RETURN','Применимая налоговая декларация и подтверждение приема',true),
('TAX_PATENT','Патент',true),
('INCOME_RECORD','Учет доходов и расходов или справка о доходах',true),
('BANK_STATEMENT','Банковская выписка',true),
('DEBT_AGREEMENT','Договор действующего кредита, займа или лизинга',true),
('DEBT_SCHEDULE','График и остаток обязательств',true),
('MANAGEMENT_ACCOUNTS','Управленческая отчетность и расшифровки',true),
('BUSINESS_PLAN','План проекта и прогноз денежных потоков',true),
('PURPOSE_CONTRACT','Договор или контракт по цели финансирования',true),
('INVOICE','Счет и спецификация',true),
('OWN_FUNDS','Подтверждение собственных средств',true),
('TITLE','Документ о правах на имущество',true),
('VALUATION','Оценка имущества',true),
('ENCUMBRANCE','Сведения об обременениях и регистрации',true),
('REQUIRED_CONSENT','Применимое согласие третьего лица',true),
('INSURANCE','Страховые документы',true),
('CREDIT_CONTRACT','Подписанный кредитный договор',true),
('GUARANTEE_CONTRACT','Договор поручительства',true),
('PLEDGE_CONTRACT','Договор залога или ипотеки',true),
('DISBURSEMENT_REQUEST','Запрос на выдачу или транш',true),
('DELIVERY_ACCEPTANCE','УПД, накладная или акт',true),
('PAYMENT_EVIDENCE','Подтверждение платежа',true),
('AMENDMENT','Дополнительное соглашение',true),
('PAYOFF_CONFIRMATION','Подтверждение погашения',true),
('SECURITY_RELEASE','Подтверждение прекращения обеспечения',true),
('OTHER','Другой документ с указанной причиной',true);

-- Roles are provisioned outside Flyway. Tests may run without the local runtime role.
DO $$
DECLARE table_name text;
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'credit_app') THEN
        GRANT USAGE ON SCHEMA credit TO credit_app;
        GRANT SELECT ON ALL TABLES IN SCHEMA credit TO credit_app;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA credit TO credit_app;
        FOREACH table_name IN ARRAY ARRAY['app_user','user_role','party','party_membership','party_relation','business_profile',
            'preliminary_profile','loan_application','application_party','application_document_requirement','requirement_document',
            'loan_offer','external_request','outbox_event']
        LOOP
            EXECUTE format('GRANT INSERT, UPDATE ON credit.%I TO credit_app', table_name);
        END LOOP;
        FOREACH table_name IN ARRAY ARRAY['recommendation_run','recommendation_item','application_revision','financial_statement',
            'document','document_version','document_review','revision_document','consent','consent_revocation',
            'application_check_requirement','check_run','assessment_run','credit_decision','loan_contract','disbursement','audit_event']
        LOOP
            EXECUTE format('GRANT INSERT ON credit.%I TO credit_app', table_name);
        END LOOP;
        -- Only the fixed-search-path SECURITY DEFINER trigger writes status history.
        REVOKE ALL ON application_status_history FROM credit_app;
        GRANT SELECT ON application_status_history TO credit_app;
        IF to_regclass('credit.flyway_schema_history') IS NOT NULL THEN
            REVOKE ALL ON credit.flyway_schema_history FROM credit_app;
        END IF;
    END IF;
END;
$$;

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA credit FROM PUBLIC;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'credit_app') THEN
        GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA credit TO credit_app;
    END IF;
END; $$;
