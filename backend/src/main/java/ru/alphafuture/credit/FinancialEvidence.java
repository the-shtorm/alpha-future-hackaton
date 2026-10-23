package ru.alphafuture.credit;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.time.*;
import java.util.*;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;

/** Отдельные финансовые операции: не расширяют 15 полей answers и не являются обучающим набором. */
@Service
class FinancialEvidence {
    static final String VERSION = "operations-revenue-1";

    enum Direction {
        CREDIT,
        DEBIT
    }

    enum Category {
        REVENUE,
        REVENUE_REFUND,
        INTERNAL_TRANSFER,
        LOAN,
        EXPENSE,
        UNKNOWN
    }

    record Operation(
            @NotBlank @Size(max = 120) String externalId,
            @NotNull LocalDate date,
            @NotBlank @Pattern(regexp = "(?:0|[1-9][0-9]{0,16})(?:\\.[0-9]{1,2})?") String amount,
            @NotNull Direction direction,
            @NotNull Category category) {}

    record Input(
            @NotNull LocalDate periodFrom,
            @NotNull LocalDate periodTo,
            @NotEmpty @Size(max = 10000) List<@Valid Operation> operations) {}

    private final JdbcClient db;
    private final Json json;
    private final Access access;

    FinancialEvidence(JdbcClient db, Json json, Access access) {
        this.db = db;
        this.json = json;
        this.access = access;
    }

    Map<String, Object> add(UUID app, Input input) {
        if (input.periodFrom().isAfter(input.periodTo())
                || input.periodTo().isAfter(LocalDate.now(ZoneOffset.UTC)))
            throw ApiFailure.invalid("period", "Нужен прошедший финансовый период");
        Set<String> ids = new HashSet<>();
        BigDecimal revenue = BigDecimal.ZERO;
        for (var op : input.operations()) {
            if (!ids.add(op.externalId()))
                throw ApiFailure.invalid("operations.externalId", "Повтор операции");
            if (op.date().isBefore(input.periodFrom()) || op.date().isAfter(input.periodTo()))
                throw ApiFailure.invalid("operations.date", "Операция вне периода");
            if (op.category() == Category.REVENUE && op.direction() == Direction.CREDIT)
                revenue = revenue.add(new BigDecimal(op.amount()));
            else if (op.category() == Category.REVENUE_REFUND && op.direction() == Direction.DEBIT)
                revenue = revenue.subtract(new BigDecimal(op.amount()));
            else if (op.category() == Category.REVENUE || op.category() == Category.REVENUE_REFUND)
                throw ApiFailure.invalid(
                        "operations.category", "Направление не соответствует категории выручки");
        }
        if (revenue.signum() < 0 || revenue.precision() - revenue.scale() > 17)
            throw ApiFailure.invalid("operations", "Некорректная сумма выручки операций");
        UUID id = UUID.randomUUID();
        db.sql(
                        "INSERT INTO credit.application_financial_evidence(id,application_id,period_from,period_to,revenue,operations,calculation_version,submitted_by) VALUES (:id,:app,:from,:to,:revenue,CAST(:operations AS jsonb),:version,:user)")
                .param("id", id)
                .param("app", app)
                .param("from", input.periodFrom())
                .param("to", input.periodTo())
                .param("revenue", revenue)
                .param("operations", json.write(input.operations()))
                .param("version", VERSION)
                .param("user", access.user())
                .update();
        return Map.of(
                "id",
                id,
                "revenue",
                revenue.toPlainString(),
                "value_status",
                "UNKNOWN",
                "calculationVersion",
                VERSION);
    }

    List<Map<String, Object>> list(UUID app) {
        var rows =
                db.sql(
                                "SELECT e.id,e.period_from AS \"periodFrom\",e.period_to AS \"periodTo\",e.revenue::text AS revenue,e.operations,e.calculation_version AS \"calculationVersion\",r.result AS \"reviewResult\",r.reason AS \"reviewReason\" FROM credit.application_financial_evidence e LEFT JOIN LATERAL (SELECT result,reason FROM credit.financial_evidence_review WHERE evidence_id=e.id ORDER BY id DESC LIMIT 1) r ON true WHERE e.application_id=:app ORDER BY e.created_at DESC,e.id")
                        .param("app", app)
                        .query()
                        .listOfRows();
        var result = new ArrayList<Map<String, Object>>();
        for (var row : rows) {
            var item = new LinkedHashMap<>(row);
            item.put("operations", json.read(row.get("operations").toString()));
            result.add(item);
        }
        return result;
    }

    Optional<UUID> latest(UUID app) {
        return db.sql(
                        "SELECT id FROM credit.application_financial_evidence WHERE application_id=:app ORDER BY created_at DESC,id DESC LIMIT 1")
                .param("app", app)
                .query(UUID.class)
                .optional();
    }

    void review(UUID app, UUID evidence, String result, String reason) {
        if (!Set.of("PASS", "FAIL", "UNKNOWN").contains(result))
            throw ApiFailure.invalid("result", "Допустимы PASS, FAIL, UNKNOWN");
        if (!db.sql(
                        "SELECT EXISTS(SELECT 1 FROM credit.application_financial_evidence WHERE application_id=:app AND id=:id)")
                .param("app", app)
                .param("id", evidence)
                .query(Boolean.class)
                .single()) throw ApiFailure.missing();
        db.sql(
                        "INSERT INTO credit.financial_evidence_review(evidence_id,result,reason,reviewed_by) VALUES (:id,:result,:reason,:user)")
                .param("id", evidence)
                .param("result", result)
                .param("reason", reason)
                .param("user", access.user())
                .update();
    }

    Map<String, Object> check(
            UUID app, UUID evidence, com.fasterxml.jackson.databind.JsonNode answers) {
        if (evidence == null) return Map.of();
        var row =
                db.sql(
                                "SELECT e.*,r.result FROM credit.application_financial_evidence e LEFT JOIN LATERAL (SELECT result FROM credit.financial_evidence_review WHERE evidence_id=e.id ORDER BY id DESC LIMIT 1) r ON true WHERE e.application_id=:app AND e.id=:id")
                        .param("app", app)
                        .param("id", evidence)
                        .query()
                        .singleRow();
        var operations = json.read(row.get("operations").toString());
        boolean unknown = false;
        for (var op : operations)
            if (op.path("category").asText().equals("UNKNOWN")) unknown = true;
        if (!"PASS".equals(row.get("result")) || unknown)
            return Map.of("missingFields", List.of("financialEvidence." + evidence));
        if (!row.get("period_from")
                        .toString()
                        .equals(FormPolicy.text(answers, "financial.periodFrom"))
                || !row.get("period_to")
                        .toString()
                        .equals(FormPolicy.text(answers, "financial.periodTo")))
            return Map.of("missingFields", List.of("financialEvidence.period"));
        BigDecimal declared = FormPolicy.money(answers, "financial.revenue"),
                observed = (BigDecimal) row.get("revenue");
        return Map.of(
                "verifiedRevenueFromOperations",
                observed.toPlainString(),
                "requiresManualReview",
                declared != null && declared.compareTo(observed) != 0,
                "comparisonRule",
                "EXACT_DECIMAL_ANY_DISCREPANCY_REQUIRES_REVIEW");
    }
}
