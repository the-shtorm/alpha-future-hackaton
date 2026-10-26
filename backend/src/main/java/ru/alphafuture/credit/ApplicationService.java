package ru.alphafuture.credit;

import com.fasterxml.jackson.databind.JsonNode;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.*;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

/** Транзакции заявки, неизменяемые ревизии и банковские команды Data Policy. */
@Service
class ApplicationService {
    record Draft(
            UUID id,
            UUID partyId,
            UUID productVersionId,
            String status,
            JsonNode answers,
            JsonNode fieldSources,
            long rowVersion,
            UUID activeRevisionId,
            UUID assignedTo,
            UUID profileId,
            Long profileVersion,
            JsonNode preliminaryContext,
            String formVersion) {}

    record HumanDecision(DataPolicy.Kind kind, String reason, List<String> missingFields) {}

    private final JdbcClient db;
    private final Access access;
    private final Json json;
    private final FormPolicy form;
    private final DataPolicy policy;
    private final Catalog catalog;
    private final Documents documents;
    private final SelectionProfiles profiles;
    private final Eligibility eligibility;
    private final FinancialEvidence financialEvidence;

    ApplicationService(
            JdbcClient db,
            Access access,
            Json json,
            FormPolicy form,
            DataPolicy policy,
            Catalog catalog,
            Documents documents,
            SelectionProfiles profiles,
            Eligibility eligibility,
            FinancialEvidence financialEvidence) {
        this.db = db;
        this.access = access;
        this.json = json;
        this.form = form;
        this.policy = policy;
        this.catalog = catalog;
        this.documents = documents;
        this.profiles = profiles;
        this.eligibility = eligibility;
        this.financialEvidence = financialEvidence;
    }

    private Draft load(UUID id, boolean bank, boolean write, boolean owner, boolean lock) {
        if (bank) access.requireBank();
        String permission =
                bank
                        ? ""
                        : " AND EXISTS(SELECT 1 FROM credit.party_membership m WHERE m.party_id=a.applicant_party_id AND m.user_id=:user AND m.revoked_at IS NULL)";
        var query =
                db.sql(
                                "SELECT a.* FROM credit.loan_application a WHERE a.id=:id"
                                        + permission
                                        + (lock ? " FOR UPDATE OF a" : ""))
                        .param("id", id);
        if (!bank) query.param("user", access.user());
        var app =
                query.query(
                                (rs, n) ->
                                        new Draft(
                                                rs.getObject("id", UUID.class),
                                                rs.getObject("applicant_party_id", UUID.class),
                                                rs.getObject("product_version_id", UUID.class),
                                                rs.getString("status"),
                                                json.read(rs.getString("draft_answers")),
                                                json.read(rs.getString("draft_field_sources")),
                                                rs.getLong("row_version"),
                                                rs.getObject("active_revision_id", UUID.class),
                                                rs.getObject("assigned_to", UUID.class),
                                                rs.getObject("preliminary_profile_id", UUID.class),
                                                rs.getObject("source_profile_version", Long.class),
                                                rs.getString("source_preliminary_snapshot") == null
                                                        ? json.mapper.createObjectNode()
                                                        : json.read(
                                                                rs.getString(
                                                                        "source_preliminary_snapshot")),
                                                rs.getString("form_version")))
                        .optional()
                        .orElseThrow(ApiFailure::missing);
        if (!bank) access.member(app.partyId(), write, owner);
        if (bank && lock && app.assignedTo() != null && !app.assignedTo().equals(access.user()))
            throw new ApiFailure(
                    409, "ASSIGNED_TO_OTHER", "Заявка закреплена за другим сотрудником");
        return app;
    }

    Draft get(UUID id) {
        return load(id, access.bank(), false, false, false);
    }

    private void editable(Draft app, long expected) {
        if (!Set.of("DRAFT", "NEEDS_INFO").contains(app.status()) || app.rowVersion() != expected)
            throw ApiFailure.conflict();
    }

    private void party(UUID id, JsonNode answers) {
        var row =
                db.sql("SELECT tax_id,party_kind FROM credit.party WHERE id=:id")
                        .param("id", id)
                        .query()
                        .singleRow();
        if (!Objects.equals(
                row.get("party_kind"), FormPolicy.text(answers, "registration.borrowerKind")))
            throw ApiFailure.invalid(
                    "registration.borrowerKind",
                    "Форма бизнеса должна соответствовать организации кабинета");
    }

    private JsonNode sources(JsonNode answers, JsonNode old, JsonNode previous) {
        var result = json.mapper.createObjectNode();
        answers.fields()
                .forEachRemaining(
                        section ->
                                section.getValue()
                                        .fields()
                                        .forEachRemaining(
                                                field -> {
                                                    if (field.getValue().isNull()) return;
                                                    String key =
                                                            section.getKey() + "." + field.getKey();
                                                    JsonNode source =
                                                            previous.has(key)
                                                                            && FormPolicy.value(
                                                                                            old,
                                                                                            key)
                                                                                    .equals(
                                                                                            field
                                                                                                    .getValue())
                                                                    ? previous.get(key)
                                                                    : json.tree(
                                                                            Map.of(
                                                                                    "kind",
                                                                                    "APPLICANT",
                                                                                    "source_code",
                                                                                    "MANUAL",
                                                                                    "verification_status",
                                                                                    "DECLARED",
                                                                                    "observed_at",
                                                                                    Instant.now()
                                                                                            .toString()));
                                                    result.set(key, source);
                                                }));
        return result;
    }

    @Transactional
    Draft create(UUID profileId, long expectedProfileVersion, JsonNode additions) {
        var source = profiles.transfer(profileId, expectedProfileVersion);
        var base = FormPolicy.project(source.answers(), FormPolicy.TRANSFER_FIELDS);
        if (additions == null || !additions.isObject())
            throw ApiFailure.invalid("answers", "Нужны поля окончательной заявки");
        form.validate(additions);
        var answers = json.merge(base, additions);
        form.validate(answers);
        var product = catalog.get(source.productVersionId(), true);
        catalog.validate(product, answers);
        party(source.partyId(), answers);
        var declared = sources(answers, base, source.sources());
        var context =
                json.tree(
                        Map.of(
                                "profileId",
                                source.id(),
                                "profileVersion",
                                source.version(),
                                "runId",
                                source.runId(),
                                "answers",
                                source.answers(),
                                "fieldSources",
                                source.sources(),
                                "formVersion",
                                FormPolicy.PRELIMINARY_VERSION));
        UUID id = UUID.randomUUID();
        db.sql(
                        "INSERT INTO credit.loan_application(id,applicant_party_id,created_by,preliminary_profile_id,product_version_id,requested_amount,requested_term_months,currency,purpose,form_version,draft_answers,draft_field_sources,workflow_mode,source_profile_version,source_preliminary_snapshot) VALUES (:id,:party,:user,:profile,:product,:amount,:term,:currency,:purpose,:form,CAST(:answers AS jsonb),CAST(:sources AS jsonb),'SIMPLIFIED',:sourceVersion,CAST(:context AS jsonb))")
                .param("id", id)
                .param("party", source.partyId())
                .param("user", access.user())
                .param("profile", source.id())
                .param("product", product.versionId())
                .param("amount", FormPolicy.money(answers, "request.amount"))
                .param("term", FormPolicy.value(answers, "request.termMonths").asInt())
                .param("currency", product.currency())
                .param("purpose", FormPolicy.text(answers, "request.purpose"))
                .param("form", FormPolicy.APPLICATION_VERSION)
                .param("answers", json.write(answers))
                .param("sources", json.write(declared))
                .param("sourceVersion", source.version())
                .param("context", json.write(context))
                .update();
        var types = new LinkedHashSet<String>();
        if (product.policy().path("collateral").path("required").asBoolean())
            types.addAll(List.of("TITLE", "VALUATION"));
        if (product.policy()
                .path("guarantor")
                .path(FormPolicy.text(answers, "registration.borrowerKind"))
                .asText()
                .endsWith("_REQUIRED")) types.add("GUARANTEE_CONTRACT");
        for (var trigger : product.policy().path("additional_document_triggers")) {
            String type =
                    switch (trigger.asText()) {
                        case "PURCHASE_DOCUMENTS", "SUPPLIER_DOCUMENTS" -> "INVOICE";
                        case "BUSINESS_PLAN", "SEASONAL_CASHFLOW" -> "BUSINESS_PLAN";
                        case "CONFIRMED_CONTRACT" -> "PURPOSE_CONTRACT";
                        case "EXISTING_LOAN" -> "DEBT_AGREEMENT";
                        default -> null;
                    };
            if (type != null) types.add(type);
        }
        for (String type : types)
            db.sql(
                            "INSERT INTO credit.application_document_requirement(application_id,subject_party_id,type_code,requirement_key,basis,reason,policy_version,required_before) VALUES (:app,:party,:type,:type,'POLICY','Требование выбранного продукта',:version,'DECISION')")
                    .param("app", id)
                    .param("party", source.partyId())
                    .param("type", type)
                    .param("version", DataPolicy.VERSION)
                    .update();
        return load(id, false, false, false, false);
    }

    @Transactional
    Draft refreshPreliminary(UUID id, long expected, long profileVersion) {
        var app = load(id, false, true, false, true);
        editable(app, expected);
        if (app.profileId() == null) throw ApiFailure.conflict();
        var source = profiles.transfer(app.profileId(), profileVersion);
        if (!source.partyId().equals(app.partyId())
                || !source.productVersionId().equals(app.productVersionId()))
            throw new ApiFailure(
                    409, "PRODUCT_CHANGED", "Для другого продукта создайте новую заявку");
        var context =
                Map.of(
                        "profileId",
                        source.id(),
                        "profileVersion",
                        source.version(),
                        "runId",
                        source.runId(),
                        "answers",
                        source.answers(),
                        "fieldSources",
                        source.sources(),
                        "formVersion",
                        FormPolicy.PRELIMINARY_VERSION);
        db.sql(
                        "UPDATE credit.loan_application SET source_profile_version=:version,source_preliminary_snapshot=CAST(:context AS jsonb),row_version=row_version+1 WHERE id=:id")
                .param("version", source.version())
                .param("context", json.write(context))
                .param("id", id)
                .update();
        return load(id, false, false, false, false);
    }

    @Transactional
    Draft patch(UUID id, long expected, JsonNode patch) {
        var app = load(id, false, true, false, true);
        editable(app, expected);
        if (patch == null || !patch.isObject())
            throw ApiFailure.invalid("answers", "Нужен объект изменений");
        // Upgrade only an editable draft. Submitted revisions and original context stay immutable.
        var base = FormPolicy.project(app.answers(), FormPolicy.APPLICATION_FIELDS);
        if (!FormPolicy.APPLICATION_VERSION.equals(app.formVersion())) {
            var inherited =
                    FormPolicy.project(
                            app.preliminaryContext().path("answers"), FormPolicy.TRANSFER_FIELDS);
            base = json.merge(inherited, base);
        }
        var answers = json.merge(base, patch);
        form.validate(answers);
        catalog.validate(catalog.get(app.productVersionId(), false), answers);
        party(app.partyId(), answers);
        db.sql(
                        "UPDATE credit.loan_application SET form_version=:form,draft_answers=CAST(:answers AS jsonb),draft_field_sources=CAST(:sources AS jsonb),requested_amount=:amount,requested_term_months=:term,purpose=:purpose,row_version=row_version+1 WHERE id=:id")
                .param("id", id)
                .param("answers", json.write(answers))
                .param("form", FormPolicy.APPLICATION_VERSION)
                .param("sources", json.write(sources(answers, app.answers(), app.fieldSources())))
                .param("amount", FormPolicy.money(answers, "request.amount"))
                .param("term", FormPolicy.value(answers, "request.termMonths").asInt())
                .param("purpose", FormPolicy.text(answers, "request.purpose"))
                .update();
        return load(id, false, false, false, false);
    }

    Map<String, Object> list(boolean bank, int page, int size) {
        if (bank) access.requireBank();
        if (page < 0 || size < 1 || size > 50)
            throw ApiFailure.invalid("page/size", "page >= 0, size от 1 до 50");
        String where =
                bank
                        ? ""
                        : " WHERE EXISTS(SELECT 1 FROM credit.party_membership m WHERE m.party_id=a.applicant_party_id AND m.user_id=:user AND m.revoked_at IS NULL)";
        var query =
                db.sql(
                                "SELECT a.id,a.applicant_party_id,a.product_version_id,a.status,a.assigned_to,a.row_version,a.created_at FROM credit.loan_application a"
                                        + where
                                        + " ORDER BY a.created_at DESC,a.id LIMIT :size OFFSET :offset")
                        .param("size", size)
                        .param("offset", (long) page * size);
        var count = db.sql("SELECT count(*) FROM credit.loan_application a" + where);
        if (!bank) {
            query.param("user", access.user());
            count.param("user", access.user());
        }
        return Map.of(
                "content",
                query.query().listOfRows(),
                "totalElements",
                count.query(Long.class).single(),
                "page",
                page,
                "size",
                size);
    }

    Map<String, Object> validate(UUID id) {
        var app = get(id);
        var result =
                review(
                        app.answers(),
                        app.preliminaryContext(),
                        catalog.get(app.productVersionId(), false),
                        Instant.now());
        return Map.of("value_status", form.statuses(app.answers()), "review", result);
    }

    @Transactional
    Map<String, Object> submit(UUID id, long expected, String key) {
        if (key == null || key.isBlank() || key.length() > 160)
            throw ApiFailure.invalid("Idempotency-Key", "Нужен ключ длиной 1..160");
        var app = load(id, false, false, true, true);
        db.sql("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))")
                .param("key", access.user() + ":" + key)
                .query()
                .singleRow();
        var existing =
                db.sql(
                                "SELECT application_id,expected_version,revision_id FROM credit.api_submission WHERE user_id=:user AND idempotency_key=:key")
                        .param("user", access.user())
                        .param("key", key)
                        .query()
                        .listOfRows();
        if (!existing.isEmpty()) {
            var previous = existing.getFirst();
            if (!previous.get("application_id").equals(id)
                    || ((Number) previous.get("expected_version")).longValue() != expected)
                throw ApiFailure.conflict();
            return Map.of("revisionId", previous.get("revision_id"), "replayed", true);
        }
        editable(app, expected);
        form.validate(app.answers());
        var product = catalog.get(app.productVersionId(), true);
        catalog.validate(product, app.answers());
        UUID revision = UUID.randomUUID();
        Instant now = Instant.now();
        var files =
                db.sql(
                                "SELECT id,sha256,type_code FROM credit.document_version WHERE application_id=:id AND type_code<>'CREDIT_CONTRACT' ORDER BY id")
                        .param("id", id)
                        .query()
                        .listOfRows();
        var snapshot =
                json.tree(
                        Map.of(
                                "answers",
                                app.answers(),
                                "fieldSources",
                                app.fieldSources(),
                                "product",
                                product,
                                "documents",
                                files,
                                "asOf",
                                now.toString(),
                                "policyVersion",
                                DataPolicy.VERSION,
                                "preliminaryContext",
                                app.preliminaryContext(),
                                "transferredAnswersConfirmed",
                                true));
        financialEvidence
                .latest(id)
                .ifPresent(
                        evidence ->
                                ((com.fasterxml.jackson.databind.node.ObjectNode) snapshot)
                                        .put("financialEvidenceId", evidence.toString()));
        String canonical = json.canonical(snapshot), hash = Json.hash(canonical);
        db.sql(
                        "INSERT INTO credit.application_revision(id,application_id,revision_no,submitted_by,form_version,product_version_id,snapshot,snapshot_sha256,submission_evidence,submitted_at) VALUES (:revision,:app,(SELECT coalesce(max(revision_no),0)+1 FROM credit.application_revision WHERE application_id=:app),:user,:form,:product,CAST(:snapshot AS jsonb),:hash,CAST(:evidence AS jsonb),:now)")
                .param("revision", revision)
                .param("form", FormPolicy.APPLICATION_VERSION)
                .param("app", id)
                .param("user", access.user())
                .param("product", app.productVersionId())
                .param("snapshot", canonical)
                .param("hash", hash)
                .param(
                        "evidence",
                        json.write(Map.of("confirmedBy", access.user(), "isSimulated", true)))
                .param("now", Timestamp.from(now))
                .update();
        for (var file : files)
            db.sql(
                            "INSERT INTO credit.revision_document(application_id,revision_id,document_version_id) VALUES (:app,:revision,:version)")
                    .param("app", id)
                    .param("revision", revision)
                    .param("version", file.get("id"))
                    .update();
        for (String gate : List.of("DECISION", "DISBURSEMENT"))
            db.sql(
                            "INSERT INTO credit.application_check_requirement(application_id,revision_id,check_code,rule_version,is_legal_gate,required_before,reason) VALUES (:app,:revision,:code,:version,false,:gate,'Проверка Data Policy')")
                    .param("app", id)
                    .param("revision", revision)
                    .param("code", "DATA_POLICY_" + gate)
                    .param("version", DataPolicy.VERSION)
                    .param("gate", gate)
                    .update();
        db.sql(
                        "UPDATE credit.loan_application SET active_revision_id=:revision,status='SUBMITTED',last_changed_by=:user,last_change_reason='Владелец подтвердил подачу',row_version=row_version+1 WHERE id=:id")
                .param("revision", revision)
                .param("user", access.user())
                .param("id", id)
                .update();
        db.sql(
                        "INSERT INTO credit.api_submission(user_id,idempotency_key,application_id,expected_version,revision_id) VALUES (:user,:key,:app,:expected,:revision)")
                .param("user", access.user())
                .param("key", key)
                .param("app", id)
                .param("expected", expected)
                .param("revision", revision)
                .update();
        return Map.of("revisionId", revision, "sha256", hash, "replayed", false);
    }

    private void transition(UUID id, String status, String reason) {
        db.sql(
                        "UPDATE credit.loan_application SET status=:status,last_changed_by=:user,last_change_reason=:reason,row_version=row_version+1 WHERE id=:id")
                .param("id", id)
                .param("status", status)
                .param("user", access.user())
                .param("reason", reason)
                .update();
    }

    @Transactional
    Draft assign(UUID id) {
        var app = load(id, true, false, false, true);
        db.sql(
                        "UPDATE credit.loan_application SET assigned_to=:user,row_version=row_version+1 WHERE id=:id AND assigned_to IS NULL")
                .param("id", id)
                .param("user", access.user())
                .update();
        return load(id, true, false, false, false);
    }

    @Transactional
    Map<String, Object> process(UUID id) {
        return decide(id, null);
    }

    @Transactional
    Map<String, Object> humanDecision(UUID id, HumanDecision decision) {
        return decide(id, decision);
    }

    private Map<String, Object> decide(UUID id, HumanDecision human) {
        var app = load(id, true, false, false, true);
        if (!Set.of("SUBMITTED", "UNDER_REVIEW").contains(app.status()))
            throw ApiFailure.conflict();
        db.sql(
                        "UPDATE credit.loan_application SET assigned_to=:user WHERE id=:id AND assigned_to IS NULL")
                .param("id", id)
                .param("user", access.user())
                .update();
        var revision =
                db.sql(
                                "SELECT snapshot,snapshot_sha256,submitted_at FROM credit.application_revision WHERE application_id=:app AND id=:revision")
                        .param("app", id)
                        .param("revision", app.activeRevisionId())
                        .query()
                        .singleRow();
        var snapshot = json.read(revision.get("snapshot").toString());
        var answers = snapshot.path("answers");
        var product = catalog.frozen(snapshot.path("product"));
        Instant asOf =
                revision.get("submitted_at") instanceof Timestamp time
                        ? time.toInstant()
                        : ((java.time.OffsetDateTime) revision.get("submitted_at")).toInstant();
        var result =
                review(
                        answers,
                        snapshot.path("preliminaryContext"),
                        product,
                        asOf,
                        snapshot.path("policyVersion").asText(LegacyDataPolicy.VERSION));
        var missing = documents.missing(id, app.activeRevisionId());
        if (!missing.isEmpty() && result.kind() != DataPolicy.Kind.DECLINED) {
            var conditions = new LinkedHashMap<>(result.conditions());
            var all = new LinkedHashSet<String>();
            for (var field : (List<?>) conditions.get("missingFields"))
                if (!field.equals("scoring")) all.add(field.toString());
            all.addAll(missing);
            conditions.put("missingFields", List.copyOf(all));
            conditions.remove("requiresManualReview");
            conditions.put("reasonCode", "DOCUMENT_CHECK_REQUIRED");
            result =
                    new DataPolicy.Review(
                            DataPolicy.Kind.REQUEST_INFO,
                            "Требуются данные или проверка документов",
                            conditions);
        }
        if (result.kind() != DataPolicy.Kind.DECLINED
                && snapshot.hasNonNull("financialEvidenceId")) {
            var checked =
                    financialEvidence.check(
                            id,
                            UUID.fromString(snapshot.path("financialEvidenceId").asText()),
                            answers);
            var conditions = new LinkedHashMap<>(result.conditions());
            conditions.put("financialEvidence", checked);
            if (checked.containsKey("missingFields")) {
                var fields = new LinkedHashSet<String>();
                for (var field : (List<?>) conditions.get("missingFields"))
                    fields.add(field.toString());
                for (var field : (List<?>) checked.get("missingFields"))
                    fields.add(field.toString());
                conditions.put("missingFields", List.copyOf(fields));
                conditions.remove("requiresManualReview");
                conditions.put("reasonCode", "FINANCIAL_EVIDENCE_REQUIRED");
                result =
                        new DataPolicy.Review(
                                DataPolicy.Kind.REQUEST_INFO,
                                "Требуется проверка финансовых операций",
                                conditions);
            } else {
                if (result.kind() != DataPolicy.Kind.REQUEST_INFO
                        && Boolean.TRUE.equals(checked.get("requiresManualReview"))) {
                    conditions.put("requiresManualReview", true);
                    conditions.put("reasonCode", "MANUAL_REVIEW_REQUIRED");
                    conditions.put("manualReviewReason", "DECLARED_VS_OPERATIONS_REVENUE_MISMATCH");
                }
                result =
                        new DataPolicy.Review(
                                result.kind(),
                                result.reason(),
                                conditions,
                                result.alternativeTerms());
            }
        }
        if (human != null) {
            if (human.kind() == DataPolicy.Kind.APPROVED
                            && result.kind() != DataPolicy.Kind.APPROVED
                    || human.kind() == DataPolicy.Kind.COUNTEROFFERED
                            && result.kind() != DataPolicy.Kind.COUNTEROFFERED)
                throw new ApiFailure(
                        422,
                        "POLICY_BLOCKED",
                        "Ручное решение не может обойти проверки, оценку и платежный бюджет");
            if (human.kind() == DataPolicy.Kind.REQUEST_INFO
                    && (human.missingFields() == null || human.missingFields().isEmpty()))
                throw ApiFailure.invalid("missingFields", "Укажите недостающие поля");
            var conditions = new LinkedHashMap<>(result.conditions());
            conditions.put("decisionSource", "BANK_APPROVER");
            conditions.put(
                    "policyReasonCode", conditions.getOrDefault("reasonCode", "POLICY_REVIEW"));
            conditions.put("reasonCode", "BANK_" + human.kind().name());
            if (Boolean.TRUE.equals(conditions.remove("requiresManualReview")))
                conditions.put("manualReviewAcknowledged", true);
            conditions.put(
                    "missingFields",
                    human.kind() == DataPolicy.Kind.REQUEST_INFO
                            ? human.missingFields()
                            : List.of());
            result =
                    new DataPolicy.Review(
                            human.kind(),
                            human.reason(),
                            conditions,
                            human.kind() == DataPolicy.Kind.COUNTEROFFERED
                                    ? result.alternativeTerms()
                                    : null);
        }
        if (app.status().equals("SUBMITTED")) {
            transition(id, "VALIDATING", "Проверка поданной ревизии");
            transition(id, "ENRICHING", "Сопоставление заявки и контекста подбора");
            transition(id, "SCORING", "Оценка сделки: режим указан в условиях решения");
        }
        boolean positive =
                result.kind() == DataPolicy.Kind.APPROVED
                        || result.kind() == DataPolicy.Kind.COUNTEROFFERED;
        UUID selectedAssessmentId = persistAssessments(app, result);
        recordCheck(
                app,
                "DECISION",
                Boolean.TRUE.equals(result.conditions().get("requiresManualReview"))
                        ? "REVIEW"
                        : positive
                                ? "PASS"
                                : result.kind() == DataPolicy.Kind.DECLINED ? "FAIL" : "REVIEW",
                result.conditions(),
                revision.get("snapshot_sha256").toString());
        if (app.status().equals("SUBMITTED")
                && (result.kind() != DataPolicy.Kind.REQUEST_INFO
                        || Boolean.TRUE.equals(result.conditions().get("requiresManualReview"))))
            transition(id, "UNDER_REVIEW", "Банковское рассмотрение");
        if (human == null && Boolean.TRUE.equals(result.conditions().get("requiresManualReview")))
            return journey(id);
        UUID decision = UUID.randomUUID();
        Instant expires = Instant.now().plusSeconds(7 * 86400);
        DataPolicy.Terms approved =
                result.kind() == DataPolicy.Kind.COUNTEROFFERED
                        ? result.alternativeTerms()
                        : new DataPolicy.Terms(
                                FormPolicy.text(answers, "request.amount"),
                                FormPolicy.value(answers, "request.termMonths").asInt(),
                                product.annualRatePct());
        String storedKind =
                result.kind() == DataPolicy.Kind.COUNTEROFFERED
                        ? "COUNTEROFFER"
                        : result.kind().name();
        db.sql(
                        "INSERT INTO credit.credit_decision(id,application_id,revision_id,assessment_id,decision_kind,decided_by,reasoning,approved_amount,approved_term_months,annual_rate_pct,conditions,valid_until) VALUES (:id,:app,:revision,:assessment,:kind,:user,:reason,:amount,:term,:rate,CAST(:conditions AS jsonb),:expires)")
                .param("id", decision)
                .param("app", id)
                .param("revision", app.activeRevisionId())
                .param("assessment", selectedAssessmentId)
                .param("kind", storedKind)
                .param("user", access.user())
                .param("reason", result.reason())
                .param("amount", positive ? new java.math.BigDecimal(approved.amount()) : null)
                .param("term", positive ? approved.termMonths() : null)
                .param("rate", positive ? new java.math.BigDecimal(approved.annualRatePct()) : null)
                .param("conditions", json.write(result.conditions()))
                .param("expires", positive ? Timestamp.from(expires) : null)
                .update();
        transition(
                id,
                result.kind() == DataPolicy.Kind.REQUEST_INFO ? "NEEDS_INFO" : result.kind().name(),
                result.reason());
        if (result.kind() == DataPolicy.Kind.APPROVED)
            issueOffer(id, decision, approved, product.currency(), expires);
        if (result.kind() == DataPolicy.Kind.COUNTEROFFERED) {
            String canonical = json.canonical(json.tree(approved));
            db.sql(
                            "INSERT INTO credit.counteroffer_proposal(application_id,revision_id,decision_id,macro_context_id,terms,terms_sha256,expires_at) VALUES (:app,:revision,:decision,:macro,CAST(:terms AS jsonb),:hash,:expiry)")
                    .param("app", id)
                    .param("revision", app.activeRevisionId())
                    .param("decision", decision)
                    .param("macro", result.conditions().get("macroContextId"))
                    .param("terms", canonical)
                    .param("hash", Json.hash(canonical))
                    .param("expiry", Timestamp.from(expires))
                    .update();
        }
        return journey(id);
    }

    private UUID issueOffer(
            UUID app, UUID decision, DataPolicy.Terms terms, String currency, Instant expires) {
        UUID offer = UUID.randomUUID();
        String canonical =
                json.canonical(
                        json.tree(
                                Map.of(
                                        "amount",
                                        terms.amount(),
                                        "termMonths",
                                        terms.termMonths(),
                                        "annualRatePct",
                                        terms.annualRatePct(),
                                        "currency",
                                        currency,
                                        "isSimulated",
                                        true)));
        db.sql(
                        "INSERT INTO credit.loan_offer(id,application_id,decision_id,version_no,terms,terms_sha256,expires_at) VALUES (:id,:app,:decision,(SELECT coalesce(max(version_no),0)+1 FROM credit.loan_offer WHERE application_id=:app),CAST(:terms AS jsonb),:hash,:expiry)")
                .param("id", offer)
                .param("app", app)
                .param("decision", decision)
                .param("terms", canonical)
                .param("hash", Json.hash(canonical))
                .param("expiry", Timestamp.from(expires))
                .update();
        return offer;
    }

    private DataPolicy.Review review(
            JsonNode answers, JsonNode context, Catalog.Product product, Instant asOf) {
        return review(answers, context, product, asOf, DataPolicy.VERSION);
    }

    private DataPolicy.Review review(
            JsonNode answers,
            JsonNode context,
            Catalog.Product product,
            Instant asOf,
            String version) {
        if (!context.has("answers"))
            return new DataPolicy.Review(
                    DataPolicy.Kind.REQUEST_INFO,
                    "Нет контекста предварительной формы",
                    Map.of(
                            "missingFields",
                            List.of("preliminaryProfile"),
                            "policyVersion",
                            version,
                            "reasonCode",
                            "PRELIMINARY_CONTEXT_REQUIRED"));
        var selection = FormPolicy.selectionContext(context.path("answers"), answers);
        try {
            form.validatePreliminary(selection);
        } catch (ApiFailure ex) {
            return new DataPolicy.Review(
                    DataPolicy.Kind.REQUEST_INFO,
                    "Неверные данные предварительной формы",
                    Map.of(
                            "missingFields",
                            ex.fields,
                            "policyVersion",
                            version,
                            "reasonCode",
                            "INVALID_APPLICATION_DATA"));
        }
        var applicable = eligibility.evaluate(product, selection, asOf);
        var initial = new LinkedHashMap<String, Object>();
        initial.put("policyVersion", version);
        initial.put("eligibility", applicable);
        initial.put("missingFields", List.of());
        if (applicable.status() == Eligibility.Status.INELIGIBLE) {
            initial.put("reasonCode", "PRODUCT_INELIGIBLE");
            return new DataPolicy.Review(
                    DataPolicy.Kind.DECLINED,
                    "Ограничения выбранного продукта не выполнены",
                    initial);
        }
        if (!applicable.missingFields().isEmpty()) {
            initial.put(
                    "missingFields",
                    applicable.missingFields().stream()
                            .map(field -> "preliminary." + field)
                            .toList());
            initial.put("reasonCode", "PRELIMINARY_DATA_REQUIRED");
            return new DataPolicy.Review(
                    DataPolicy.Kind.REQUEST_INFO, "Нужно дополнить предварительную форму", initial);
        }
        var result = policy.review(answers, product, asOf, version);
        var conditions = new LinkedHashMap<>(result.conditions());
        conditions.put("eligibility", applicable);
        if (result.kind() != DataPolicy.Kind.REQUEST_INFO
                && result.kind() != DataPolicy.Kind.DECLINED
                && applicable.reasons().stream()
                        .anyMatch(reason -> reason.result() == Eligibility.Outcome.REVIEW)) {
            conditions.put("requiresManualReview", true);
            conditions.put("reasonCode", "MANUAL_REVIEW_REQUIRED");
            conditions.put(
                    "manualReviewReasons",
                    applicable.reasons().stream()
                            .filter(reason -> reason.result() == Eligibility.Outcome.REVIEW)
                            .map(Eligibility.Reason::code)
                            .distinct()
                            .toList());
        }
        return new DataPolicy.Review(
                result.kind(), result.reason(), conditions, result.alternativeTerms());
    }

    private UUID persistAssessments(Draft app, DataPolicy.Review review) {
        Object raw = review.conditions().get("scoringAssessments");
        if (!(raw instanceof List<?> assessments) || assessments.isEmpty()) return null;
        var ids = new ArrayList<UUID>();
        for (Object value : assessments) {
            var assessment = (ScoringExchange.Assessment) value;
            var input = json.tree(assessment.request());
            var normalized = (com.fasterxml.jackson.databind.node.ObjectNode) input.deepCopy();
            normalized.remove("requestId");
            UUID id = UUID.randomUUID();
            db.sql(
                            "INSERT INTO credit.assessment_run(id,application_id,revision_id,assessment_kind,model_version,feature_version,input_sha256,input_manifest,output,is_synthetic) VALUES (:id,:app,:revision,'SCORING',:model,:features,:hash,CAST(:input AS jsonb),CAST(:output AS jsonb),true)")
                    .param("id", id)
                    .param("app", app.id())
                    .param("revision", app.activeRevisionId())
                    .param("model", assessment.response().modelVersion())
                    .param("features", assessment.response().featureVersion())
                    .param("hash", Json.hash(json.canonical(normalized)))
                    .param("input", json.write(input))
                    .param("output", json.write(assessment.response()))
                    .update();
            ids.add(id);
        }
        review.conditions().put("assessmentIds", List.copyOf(ids));
        return ids.get("ALTERNATIVE".equals(review.conditions().get("selectedVariant")) ? 1 : 0);
    }

    @Transactional
    Map<String, Object> acceptCounteroffer(UUID id, UUID proposal, String termsHash) {
        var app = load(id, false, false, true, true);
        var row =
                db
                        .sql(
                                "SELECT p.*,a.offer_id FROM credit.counteroffer_proposal p LEFT JOIN credit.counteroffer_acceptance a ON a.proposal_id=p.id WHERE p.application_id=:app AND p.id=:proposal")
                        .param("app", id)
                        .param("proposal", proposal)
                        .query()
                        .listOfRows()
                        .stream()
                        .findFirst()
                        .orElseThrow(ApiFailure::missing);
        if (!row.get("terms_sha256").equals(termsHash))
            throw new ApiFailure(409, "TERMS_CHANGED", "Подтвердите точные сохраненные условия");
        if (row.get("offer_id") != null) return journey(id);
        Instant expires =
                row.get("expires_at") instanceof Timestamp ts
                        ? ts.toInstant()
                        : ((java.time.OffsetDateTime) row.get("expires_at")).toInstant();
        if (!app.status().equals("COUNTEROFFERED")
                || !row.get("revision_id").equals(app.activeRevisionId())
                || !expires.isAfter(Instant.now())) throw ApiFailure.conflict();
        var terms = json.read(row.get("terms").toString());
        UUID offer =
                issueOffer(
                        id,
                        (UUID) row.get("decision_id"),
                        new DataPolicy.Terms(
                                terms.path("amount").asText(),
                                terms.path("termMonths").asInt(),
                                terms.path("annualRatePct").asText()),
                        catalog.get(app.productVersionId(), false).currency(),
                        expires);
        db.sql(
                        "UPDATE credit.loan_offer SET response='ACCEPTED',responded_by=:user,responded_at=now(),response_evidence=CAST(:evidence AS jsonb) WHERE id=:offer")
                .param("user", access.user())
                .param(
                        "evidence",
                        json.write(
                                Map.of(
                                        "proposalId",
                                        proposal,
                                        "termsSha256",
                                        termsHash,
                                        "confirmedBy",
                                        access.user(),
                                        "isSimulated",
                                        true)))
                .param("offer", offer)
                .update();
        db.sql(
                        "INSERT INTO credit.counteroffer_acceptance(proposal_id,application_id,offer_id,accepted_by,terms_sha256) VALUES (:proposal,:app,:offer,:user,:hash)")
                .param("proposal", proposal)
                .param("app", id)
                .param("offer", offer)
                .param("user", access.user())
                .param("hash", termsHash)
                .update();
        transition(id, "OFFER_ACCEPTED", "Владелец принял встречное предложение");
        return journey(id);
    }

    private void recordCheck(
            Draft app, String gate, String result, Map<String, Object> evidence, String hash) {
        db.sql(
                        "INSERT INTO credit.check_run(application_id,revision_id,check_code,rule_version,result,is_legal_gate,input_sha256,evidence) VALUES (:app,:revision,:code,:version,:result,false,:hash,CAST(:evidence AS jsonb))")
                .param("app", app.id())
                .param("revision", app.activeRevisionId())
                .param("code", "DATA_POLICY_" + gate)
                .param(
                        "version",
                        db.sql(
                                        "SELECT coalesce(snapshot->>'policyVersion','data-policy-2.1') FROM credit.application_revision WHERE application_id=:app AND id=:revision")
                                .param("app", app.id())
                                .param("revision", app.activeRevisionId())
                                .query(String.class)
                                .single())
                .param("result", result)
                .param("hash", hash)
                .param("evidence", json.write(evidence))
                .update();
    }

    Map<String, Object> journey(UUID id) {
        var app = get(id);
        var result = new LinkedHashMap<String, Object>();
        result.put("application", app);
        result.put(
                "history",
                db.sql(
                                "SELECT from_status AS \"fromStatus\",to_status AS \"toStatus\",reason,created_at AS \"createdAt\" FROM credit.application_status_history WHERE application_id=:app ORDER BY id")
                        .param("app", id)
                        .query()
                        .listOfRows());
        var checks =
                db.sql(
                                "SELECT DISTINCT ON (c.check_code) c.check_code AS \"checkCode\",c.rule_version AS \"ruleVersion\",c.result,c.evidence,c.created_at AS \"createdAt\" FROM credit.check_run c JOIN credit.loan_application a ON a.id=c.application_id AND a.active_revision_id=c.revision_id WHERE c.application_id=:app ORDER BY c.check_code,c.run_number DESC")
                        .param("app", id)
                        .query()
                        .listOfRows();
        var explained = new ArrayList<Map<String, Object>>();
        for (var row : checks) {
            var check = new LinkedHashMap<>(row);
            check.put("evidence", json.read(row.get("evidence").toString()));
            explained.add(check);
        }
        result.put("checks", explained);
        var decisions =
                db.sql(
                                "SELECT id,revision_id AS \"revisionId\",decision_kind AS kind,reasoning AS reason,conditions,decided_at AS \"decidedAt\" FROM credit.credit_decision WHERE application_id=:app ORDER BY decision_number DESC LIMIT 1")
                        .param("app", id)
                        .query()
                        .listOfRows();
        if (!decisions.isEmpty()) {
            var decision = new LinkedHashMap<>(decisions.getFirst());
            decision.put("conditions", json.read(decision.get("conditions").toString()));
            if (decision.get("kind").equals("COUNTEROFFER")) decision.put("kind", "COUNTEROFFERED");
            result.put("decision", decision);
        }
        var offers =
                db.sql(
                                "SELECT o.id,o.decision_id AS \"decisionId\",o.terms,o.terms_sha256 AS \"termsSha256\",o.expires_at AS \"expiresAt\",o.response FROM credit.loan_offer o JOIN credit.credit_decision d ON d.id=o.decision_id JOIN credit.loan_application a ON a.id=o.application_id WHERE o.application_id=:app AND d.revision_id=a.active_revision_id AND d.decision_number=(SELECT max(decision_number) FROM credit.credit_decision WHERE application_id=:app) ORDER BY o.version_no DESC LIMIT 1")
                        .param("app", id)
                        .query()
                        .listOfRows();
        if (!offers.isEmpty()) {
            var offer = new LinkedHashMap<>(offers.getFirst());
            offer.put("terms", json.read(offer.get("terms").toString()));
            result.put("offer", offer);
        }
        var proposals =
                db.sql(
                                "SELECT p.id,p.revision_id,p.decision_id,p.terms,p.terms_sha256,p.expires_at FROM credit.counteroffer_proposal p JOIN credit.loan_application a ON a.id=p.application_id JOIN credit.credit_decision d ON d.id=p.decision_id WHERE p.application_id=:app AND p.revision_id=a.active_revision_id AND d.decision_number=(SELECT max(decision_number) FROM credit.credit_decision WHERE application_id=:app) ORDER BY p.created_at DESC LIMIT 1")
                        .param("app", id)
                        .query()
                        .listOfRows();
        if (!proposals.isEmpty()) {
            var row = proposals.getFirst();
            var proposal = new LinkedHashMap<String, Object>();
            proposal.put("id", row.get("id"));
            proposal.put("revisionId", row.get("revision_id"));
            proposal.put("decisionId", row.get("decision_id"));
            proposal.put("termsSha256", row.get("terms_sha256"));
            proposal.put("expiresAt", row.get("expires_at"));
            proposal.put("alternative_terms", json.read(row.get("terms").toString()));
            result.put("counteroffer", proposal);
            if (result.get("decision") instanceof Map<?, ?> decision
                    && Objects.equals(decision.get("id"), row.get("decision_id"))) {
                var augmented = new LinkedHashMap<String, Object>();
                decision.forEach((key, value) -> augmented.put(key.toString(), value));
                augmented.put("alternative_terms", proposal.get("alternative_terms"));
                result.put("decision", augmented);
            }
        }
        result.put(
                "contracts",
                db.sql(
                                "SELECT id,offer_id AS \"offerId\",contract_number AS \"contractNumber\",signed_at AS \"signedAt\",is_simulated AS \"isSimulated\" FROM credit.loan_contract WHERE application_id=:app")
                        .param("app", id)
                        .query()
                        .listOfRows());
        result.put(
                "disbursements",
                db.sql(
                                "SELECT id,amount::text AS amount,currency,executed_at AS \"executedAt\",is_simulated AS \"isSimulated\" FROM credit.disbursement WHERE application_id=:app")
                        .param("app", id)
                        .query()
                        .listOfRows());
        return result;
    }

    Map<String, Object> revision(UUID id, UUID revision) {
        get(id);
        var row =
                db
                        .sql(
                                "SELECT id,revision_no,snapshot,snapshot_sha256,submitted_at FROM credit.application_revision WHERE application_id=:app AND id=:revision")
                        .param("app", id)
                        .param("revision", revision)
                        .query()
                        .listOfRows()
                        .stream()
                        .findFirst()
                        .orElseThrow(ApiFailure::missing);
        var result = new LinkedHashMap<>(row);
        result.put("snapshot", json.read(row.get("snapshot").toString()));
        return result;
    }

    List<Map<String, Object>> requirements(UUID id) {
        get(id);
        return db.sql(
                        "SELECT id,type_code,requirement_key,required_before,status,reason FROM credit.application_document_requirement WHERE application_id=:app ORDER BY requirement_key")
                .param("app", id)
                .query()
                .listOfRows();
    }

    List<Map<String, Object>> financialEvidence(UUID id) {
        get(id);
        return financialEvidence.list(id);
    }

    @Transactional
    Map<String, Object> addFinancialEvidence(UUID id, FinancialEvidence.Input input) {
        var app = load(id, false, true, false, true);
        if (!Set.of("DRAFT", "NEEDS_INFO").contains(app.status())) throw ApiFailure.conflict();
        var result = financialEvidence.add(id, input);
        db.sql("UPDATE credit.loan_application SET row_version=row_version+1 WHERE id=:id")
                .param("id", id)
                .update();
        return result;
    }

    @Transactional
    void reviewFinancialEvidence(UUID id, UUID evidence, String result, String reason) {
        var app = load(id, true, false, false, true);
        if (!Set.of("DRAFT", "SUBMITTED", "NEEDS_INFO", "UNDER_REVIEW").contains(app.status()))
            throw ApiFailure.conflict();
        financialEvidence.review(id, evidence, result, reason);
    }

    @Transactional
    Map<String, Object> upload(UUID id, String type, MultipartFile file) {
        var app = load(id, false, true, false, true);
        if (!Set.of("DRAFT", "NEEDS_INFO").contains(app.status())) throw ApiFailure.conflict();
        var result = documents.upload(app, type, file);
        db.sql("UPDATE credit.loan_application SET row_version=row_version+1 WHERE id=:id")
                .param("id", id)
                .update();
        return result;
    }

    @Transactional
    void reviewDocument(UUID id, UUID version, String result, String reason) {
        var app = load(id, true, false, false, true);
        if (!Set.of("DRAFT", "SUBMITTED", "NEEDS_INFO").contains(app.status()))
            throw ApiFailure.conflict();
        documents.review(id, version, result, reason);
    }

    @Transactional
    Map<String, Object> accept(UUID id, UUID offer) {
        var app = load(id, false, false, true, true);
        if (!app.status().equals("APPROVED")) throw ApiFailure.conflict();
        int changed =
                db.sql(
                                "UPDATE credit.loan_offer SET response='ACCEPTED',responded_by=:user,responded_at=now(),response_evidence=CAST(:evidence AS jsonb) WHERE application_id=:app AND id=:offer AND response IS NULL AND expires_at>now()")
                        .param("user", access.user())
                        .param("app", id)
                        .param("offer", offer)
                        .param(
                                "evidence",
                                json.write(
                                        Map.of("confirmedBy", access.user(), "isSimulated", true)))
                        .update();
        if (changed != 1) throw ApiFailure.conflict();
        transition(id, "OFFER_ACCEPTED", "Владелец принял предложение");
        return journey(id);
    }

    @Transactional
    Map<String, Object> sign(UUID id) {
        var app = load(id, false, false, true, true);
        if (!app.status().equals("OFFER_ACCEPTED")) throw ApiFailure.conflict();
        UUID offer =
                db.sql(
                                "SELECT o.id FROM credit.loan_offer o JOIN credit.credit_decision d ON d.id=o.decision_id WHERE o.application_id=:app AND o.response='ACCEPTED' AND d.revision_id=:revision AND o.expires_at>now()")
                        .param("app", id)
                        .param("revision", app.activeRevisionId())
                        .query(UUID.class)
                        .optional()
                        .orElseThrow(ApiFailure::conflict);
        UUID document = documents.contract(app, offer);
        db.sql(
                        "INSERT INTO credit.loan_contract(application_id,offer_id,contract_number,signed_document_version_id,signed_at,signature_evidence,is_simulated) VALUES (:app,:offer,:number,:document,now(),CAST(:evidence AS jsonb),true)")
                .param("app", id)
                .param("offer", offer)
                .param("number", "DEMO-" + UUID.randomUUID())
                .param("document", document)
                .param(
                        "evidence",
                        json.write(Map.of("confirmedBy", access.user(), "isSimulated", true)))
                .update();
        transition(id, "SIGNED", "Условное подписание договора");
        return journey(id);
    }

    @Transactional
    Map<String, Object> disburse(UUID id) {
        var app = load(id, true, false, false, true);
        if (!app.status().equals("SIGNED")) throw ApiFailure.conflict();
        var row =
                db.sql(
                                "SELECT c.id,d.approved_amount,o.terms FROM credit.loan_contract c JOIN credit.loan_offer o ON o.id=c.offer_id JOIN credit.credit_decision d ON d.id=o.decision_id WHERE c.application_id=:app AND d.revision_id=:revision")
                        .param("app", id)
                        .param("revision", app.activeRevisionId())
                        .query()
                        .singleRow();
        String hash =
                db.sql("SELECT snapshot_sha256 FROM credit.application_revision WHERE id=:revision")
                        .param("revision", app.activeRevisionId())
                        .query(String.class)
                        .single();
        recordCheck(
                app,
                "DISBURSEMENT",
                "PASS",
                Map.of("contractId", row.get("id"), "isSimulated", true),
                hash);
        transition(id, "READY_FOR_DISBURSEMENT", "Договор подтвержден, проверены условия выдачи");
        db.sql(
                        "INSERT INTO credit.disbursement(application_id,contract_id,operation_key,amount,currency,evidence,is_simulated) VALUES (:app,:contract,:operation,:amount,:currency,CAST(:evidence AS jsonb),true)")
                .param("app", id)
                .param("contract", row.get("id"))
                .param("operation", "demo-" + id)
                .param("amount", row.get("approved_amount"))
                .param("currency", json.read(row.get("terms").toString()).path("currency").asText())
                .param(
                        "evidence",
                        json.write(Map.of("confirmedBy", access.user(), "isSimulated", true)))
                .update();
        transition(id, "DISBURSED", "Демонстрационная выдача без перевода денег");
        return journey(id);
    }
}
