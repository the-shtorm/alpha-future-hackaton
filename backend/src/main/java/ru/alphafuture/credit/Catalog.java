package ru.alphafuture.credit;

import com.fasterxml.jackson.databind.JsonNode;
import java.math.BigDecimal;
import java.util.*;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;

/** Каталог существующих версий продукта; точные условия фиксируются в ревизии. */
@Service
class Catalog {
    record Product(
            UUID id,
            UUID versionId,
            String code,
            String name,
            String currency,
            String minAmount,
            String maxAmount,
            int minTermMonths,
            int maxTermMonths,
            String annualRatePct,
            JsonNode borrowerKinds,
            JsonNode purposes,
            JsonNode policy,
            boolean synthetic) {
        BigDecimal rate() {
            return annualRatePct == null ? null : new BigDecimal(annualRatePct);
        }
    }

    private final JdbcClient db;
    private final Json json;
    private static final String COLUMNS =
            "SELECT p.id,v.id AS version_id,p.code,p.name,v.currency,v.min_amount,v.max_amount,v.min_term_months,v.max_term_months,v.annual_rate_pct,v.allowed_borrower_kinds,v.allowed_purposes,v.policy,p.is_synthetic FROM credit.credit_product p JOIN credit.credit_product_version v ON v.product_id=p.id ";
    private static final String ACTIVE =
            "p.active AND v.effective_from<=now() AND (v.effective_to IS NULL OR v.effective_to>now())";

    Catalog(JdbcClient db, Json json) {
        this.db = db;
        this.json = json;
    }

    Map<String, Object> list(int page, int size) {
        if (page < 0 || size < 1 || size > 50)
            throw ApiFailure.invalid("page/size", "page >= 0; size от 1 до 50");
        var rows =
                db.sql(
                                COLUMNS
                                        + "WHERE "
                                        + ACTIVE
                                        + " ORDER BY p.name,p.id,v.id LIMIT :size OFFSET :offset")
                        .param("size", size)
                        .param("offset", (long) page * size)
                        .query(this::map)
                        .list();
        long total =
                db.sql(
                                "SELECT count(*) FROM credit.credit_product p JOIN credit.credit_product_version v ON v.product_id=p.id WHERE "
                                        + ACTIVE)
                        .query(Long.class)
                        .single();
        return Map.of("content", rows, "page", page, "size", size, "totalElements", total);
    }

    Product get(UUID id, boolean active) {
        return db.sql(
                        COLUMNS
                                + "WHERE (v.id=:id OR p.id=:id) "
                                + (active ? "AND " + ACTIVE : "")
                                + " ORDER BY v.effective_from DESC LIMIT 1")
                .param("id", id)
                .query(this::map)
                .optional()
                .orElseThrow(ApiFailure::missing);
    }

    List<Product> all() {
        return db.sql(COLUMNS + "WHERE " + ACTIVE + " ORDER BY p.code,v.id")
                .query(this::map)
                .list();
    }

    void validate(Product product, JsonNode answers) {
        for (String field :
                List.of(
                        "request.amount",
                        "request.termMonths",
                        "request.purpose",
                        "registration.borrowerKind"))
            if (FormPolicy.text(answers, field) == null)
                throw ApiFailure.invalid(field, "Обязательное поле для заявки");
        BigDecimal amount = FormPolicy.money(answers, "request.amount");
        int term = FormPolicy.value(answers, "request.termMonths").asInt();
        if (amount.compareTo(new BigDecimal(product.minAmount())) < 0
                || amount.compareTo(new BigDecimal(product.maxAmount())) > 0)
            throw ApiFailure.invalid("request.amount", "Сумма вне диапазона продукта");
        if (term < product.minTermMonths() || term > product.maxTermMonths())
            throw ApiFailure.invalid("request.termMonths", "Срок вне диапазона продукта");
        if (!contains(
                product.borrowerKinds(), FormPolicy.text(answers, "registration.borrowerKind")))
            throw ApiFailure.invalid(
                    "registration.borrowerKind", "Продукт недоступен для формы бизнеса");
        if (!contains(product.purposes(), FormPolicy.text(answers, "request.purpose")))
            throw ApiFailure.invalid("request.purpose", "Цель не поддерживается продуктом");
    }

    private boolean contains(JsonNode values, String value) {
        for (var item : values) if (item.asText().equals(value)) return true;
        return false;
    }

    private JsonNode describedPolicy(JsonNode raw) {
        var policy = (com.fasterxml.jackson.databind.node.ObjectNode) raw.deepCopy();
        policy.put("backendPolicyVersion", DataPolicy.VERSION);
        policy.set("applicationFields", json.tree(FormPolicy.APPLICATION_FIELDS));
        var required = new TreeSet<>(FormPolicy.TRANSFER_FIELDS);
        required.addAll(List.of("financial.monthlyDebtPayment", "financial.overdue"));
        if (policy.path("collateral").path("required").asBoolean())
            required.add("security.collateralValue");
        if (policy.path("collateral").path("min_own_contribution_pct").decimalValue().signum() > 0)
            required.add("project.ownContributionPct");
        policy.set("requiredApplicationFields", json.tree(required));
        if (!policy.has("counteroffer"))
            policy.set(
                    "counteroffer",
                    json.tree(
                            Map.of(
                                    "allowed",
                                    policy.path("repayment").asText().equals("ANNUITY")
                                            && policy.path("facility_kind").asText().equals("TERM"),
                                    "allowedChanges",
                                    List.of("AMOUNT_DECREASE", "RATE_INCREASE"),
                                    "termChangeAllowed",
                                    false,
                                    "maxAnnualRatePct",
                                    "100.00000",
                                    "policyVersion",
                                    "synthetic-counteroffer-2.1")));
        // Numeric cap is part of synthetic policy, never described as a real bank tariff.
        if (policy.at("/counteroffer/maxAnnualRatePct").isTextual())
            ((com.fasterxml.jackson.databind.node.ObjectNode) policy.get("counteroffer"))
                    .put(
                            "maxAnnualRatePct",
                            new BigDecimal(policy.at("/counteroffer/maxAnnualRatePct").asText()));
        return policy;
    }

    Product frozen(JsonNode snapshot) {
        try {
            return json.mapper.treeToValue(snapshot, Product.class);
        } catch (Exception ex) {
            throw new IllegalStateException("Stored product snapshot is invalid", ex);
        }
    }

    private Product map(java.sql.ResultSet rs, int index) throws java.sql.SQLException {
        return new Product(
                rs.getObject("id", UUID.class),
                rs.getObject("version_id", UUID.class),
                rs.getString("code"),
                rs.getString("name"),
                rs.getString("currency"),
                rs.getString("min_amount"),
                rs.getString("max_amount"),
                rs.getInt("min_term_months"),
                rs.getInt("max_term_months"),
                rs.getString("annual_rate_pct"),
                json.read(rs.getString("allowed_borrower_kinds")),
                json.read(rs.getString("allowed_purposes")),
                describedPolicy(json.read(rs.getString("policy"))),
                rs.getBoolean("is_synthetic"));
    }
}
