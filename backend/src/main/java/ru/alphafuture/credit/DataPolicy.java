package ru.alphafuture.credit;

import com.fasterxml.jackson.databind.JsonNode;
import java.math.*;
import java.time.*;
import java.time.temporal.ChronoUnit;
import java.util.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

/** Политика SBA 3.0: точный аннуитет, ML-риск, повторная оценка контрпредложения. */
@Component
class DataPolicy {
    static final String VERSION = "data-policy-3.0-sba-annuity-1";

    enum Kind {
        APPROVED,
        COUNTEROFFERED,
        DECLINED,
        REQUEST_INFO
    }

    record Terms(String amount, int termMonths, String annualRatePct) {}

    record Review(
            Kind kind, String reason, Map<String, Object> conditions, Terms alternativeTerms) {
        Review(Kind kind, String reason, Map<String, Object> conditions) {
            this(kind, reason, conditions, null);
        }
    }

    private final FormPolicy form;
    private final Payments payments;
    private final MacroContext macro;
    private final ScoringGateway scoring;
    private final LegacyDataPolicy legacy;
    private final boolean legacyDefault;

    @Autowired
    DataPolicy(
            FormPolicy form,
            Payments payments,
            MacroContext macro,
            ScoringGateway scoring,
            LegacyDataPolicy legacy) {
        this.form = form;
        this.payments = payments;
        this.macro = macro;
        this.scoring = scoring;
        this.legacy = legacy;
        this.legacyDefault = false;
    }

    /** Явный конструктор исторической политики для регрессионных тестов 2.1. */
    DataPolicy(FormPolicy form, Payments payments, DemoAssessment demo, MacroContext macro) {
        this.form = form;
        this.payments = payments;
        this.macro = macro;
        this.scoring = null;
        this.legacy = new LegacyDataPolicy(form, payments, demo, macro);
        this.legacyDefault = true;
    }

    Review review(JsonNode answers, Catalog.Product product, Instant asOf) {
        return review(answers, product, asOf, legacyDefault ? LegacyDataPolicy.VERSION : VERSION);
    }

    Review review(JsonNode answers, Catalog.Product product, Instant asOf, String version) {
        if (LegacyDataPolicy.VERSION.equals(version)) return legacy.review(answers, product, asOf);
        if (!VERSION.equals(version))
            return new Review(
                    Kind.REQUEST_INFO,
                    "Версия политики не поддерживается",
                    Map.of(
                            "policyVersion",
                            version,
                            "reasonCode",
                            "POLICY_VERSION_UNSUPPORTED",
                            "missingFields",
                            List.of("policyVersion")));
        return reviewNew(answers, product, asOf);
    }

    private Review reviewNew(JsonNode answers, Catalog.Product product, Instant asOf) {
        var conditions = new LinkedHashMap<String, Object>();
        conditions.put("isSimulated", product.synthetic());
        try {
            form.validate(answers);
        } catch (ApiFailure ex) {
            return result(
                    Kind.REQUEST_INFO,
                    "INVALID_APPLICATION_DATA",
                    ex.getMessage(),
                    conditions,
                    ex.fields,
                    null);
        }
        var statuses = form.statuses(answers);
        conditions.put("value_status", statuses);
        var overdueNode = FormPolicy.value(answers, "financial.overdue");
        if (overdueNode.isNumber()
                && overdueNode.decimalValue().compareTo(new BigDecimal("0.2")) > 0) {
            conditions.put("counterofferAllowed", false);
            return result(
                    Kind.DECLINED,
                    "OVERDUE_HARD_LIMIT",
                    "Доля просрочек превышает 20%; встречное предложение запрещено",
                    conditions,
                    List.of(),
                    null);
        }
        var required = new TreeSet<>(FormPolicy.TRANSFER_FIELDS);
        required.addAll(List.of("financial.monthlyDebtPayment", "financial.overdue"));
        var collateral = product.policy().path("collateral");
        if (collateral.path("required").asBoolean()
                || "YES".equals(FormPolicy.text(answers, "security.collateralReady")))
            required.add("security.collateralValue");
        if (collateral.path("min_own_contribution_pct").decimalValue().signum() > 0)
            required.add("project.ownContributionPct");
        var missing =
                required.stream()
                        .filter(path -> statuses.get(path) != FormPolicy.ValueStatus.KNOWN)
                        .toList();
        if (!missing.isEmpty())
            return result(
                    Kind.REQUEST_INFO,
                    "APPLICATION_FIELDS_REQUIRED",
                    "Не хватает данных окончательной заявки",
                    conditions,
                    missing,
                    null);
        Long months = Eligibility.periodMonths(answers);
        if (months == null)
            return result(
                    Kind.REQUEST_INFO,
                    "FULL_REVENUE_PERIOD_REQUIRED",
                    "Нужен период полных календарных месяцев",
                    conditions,
                    List.of("financial.periodFrom", "financial.periodTo"),
                    null);
        BigDecimal revenue = FormPolicy.money(answers, "financial.revenue"),
                existing = FormPolicy.money(answers, "financial.monthlyDebtPayment"),
                amount = FormPolicy.money(answers, "request.amount"),
                overdue = overdueNode.decimalValue();
        if (revenue.signum() == 0)
            return result(
                    Kind.REQUEST_INFO,
                    "ZERO_REVENUE",
                    "При нулевой выручке отношение не определено",
                    conditions,
                    List.of("financial.revenue"),
                    null);
        BigDecimal monthCount = BigDecimal.valueOf(months),
                average = revenue.divide(monthCount, 8, RoundingMode.HALF_UP),
                debtRatio = existing.multiply(monthCount).divide(revenue, 12, RoundingMode.HALF_UP),
                amountRatio = amount.multiply(monthCount).divide(revenue, 12, RoundingMode.HALF_UP);
        BigDecimal budget =
                revenue.multiply(new BigDecimal("0.40"))
                        .divide(monthCount, 32, RoundingMode.DOWN)
                        .subtract(existing)
                        .setScale(2, RoundingMode.DOWN);
        long age =
                ChronoUnit.MONTHS.between(
                        FormPolicy.date(answers, "business.actualStartedOn"),
                        asOf.atZone(ZoneOffset.UTC).toLocalDate());
        conditions.put("averageMonthlyRevenue", average.toPlainString());
        conditions.put("periodMonths", months);
        conditions.put("existingMonthlyDebtPayment", existing.toPlainString());
        conditions.put("paymentToRevenue", debtRatio);
        conditions.put("amountToMonthlyRevenue", amountRatio);
        conditions.put("newLoanPaymentBudget", budget.toPlainString());
        conditions.put("overdue", overdue);
        conditions.put("operatingAgeMonths", age);
        BigDecimal own = FormPolicy.money(answers, "project.ownContributionPct");
        if (own != null)
            conditions.put("ownContributionShare", own.movePointLeft(2).toPlainString());
        if (own != null
                && own.compareTo(collateral.path("min_own_contribution_pct").decimalValue()) < 0)
            return result(
                    Kind.DECLINED,
                    "OWN_CONTRIBUTION_TOO_LOW",
                    "Недостаточно собственных средств для продукта",
                    conditions,
                    List.of(),
                    null);
        BigDecimal maxPrincipal = new BigDecimal(product.maxAmount());
        BigDecimal value = FormPolicy.money(answers, "security.collateralValue");
        if ((collateral.path("required").asBoolean()
                        || "YES".equals(FormPolicy.text(answers, "security.collateralReady")))
                && (value == null || value.signum() <= 0))
            return result(
                    Kind.REQUEST_INFO,
                    "COLLATERAL_VALUE_REQUIRED",
                    "Нужна положительная стоимость обеспечения",
                    conditions,
                    List.of("security.collateralValue"),
                    null);
        if (collateral.path("max_ltv").isNumber() && value != null)
            maxPrincipal =
                    maxPrincipal.min(
                            value.multiply(collateral.path("max_ltv").decimalValue())
                                    .setScale(2, RoundingMode.DOWN));
        if (budget.signum() <= 0)
            return result(
                    Kind.DECLINED,
                    "NO_NEW_LOAN_BUDGET",
                    "После текущих обязательств нет платежного бюджета для нового кредита",
                    conditions,
                    List.of(),
                    null);
        int term = FormPolicy.value(answers, "request.termMonths").asInt();
        var originalPayment = payments.monthly(product, amount, term, product.rate());
        if (originalPayment.isEmpty())
            return result(
                    Kind.REQUEST_INFO,
                    "PAYMENT_SCHEDULE_REQUIRED",
                    "Для продукта нужен согласованный график платежей",
                    conditions,
                    List.of("product.paymentSchedule"),
                    null);
        conditions.put("estimatedFirstMonthPayment", originalPayment.get().toPlainString());
        conditions.put("totalMonthlyPayment", originalPayment.get().add(existing).toPlainString());
        var context = macro.current();
        if (context.isEmpty())
            return result(
                    Kind.REQUEST_INFO,
                    "MACRO_CONTEXT_REQUIRED",
                    "Нужен действующий макроконтекст",
                    conditions,
                    List.of("macroeconomic.key_rate_pct"),
                    null);
        conditions.put("macroeconomic", context.get());
        conditions.put("macroContextId", context.get().id());
        conditions.put("key_rate_pct", context.get().keyRatePct());
        conditions.put("fxRateRubPerUsd", ScoringExchange.FX.toPlainString());
        conditions.put("mode", "SBA_DEMO");
        if (!product.synthetic()) return unavailable(conditions, "SBA_DEMO_PRODUCT_REQUIRED");
        conditions.put("isSimulated", true);
        if (!"RUB".equals(product.currency())
                || amount.compareTo(new BigDecimal(product.minAmount())) < 0
                || amount.compareTo(new BigDecimal(product.maxAmount())) > 0
                || term < product.minTermMonths()
                || term > product.maxTermMonths())
            return result(
                    Kind.REQUEST_INFO,
                    "PRODUCT_TERMS_INVALID",
                    "Условия вне границ выбранного продукта",
                    conditions,
                    List.of("product"),
                    null);
        if (collateral.path("required").asBoolean()
                && !"YES".equals(FormPolicy.text(answers, "security.collateralReady")))
            return result(
                    Kind.REQUEST_INFO,
                    "COLLATERAL_REQUIRED",
                    "Нужно подтверждённое обеспечение",
                    conditions,
                    List.of("security.collateralReady"),
                    null);
        var assessments = new ArrayList<ScoringExchange.Assessment>();
        conditions.put("scoringAssessments", assessments);
        ScoringExchange.Assessment initial;
        try {
            initial = assess(answers, product, asOf, amount, term, product.rate());
        } catch (ScoringGateway.Failure failure) {
            return unavailable(conditions, failure.code);
        }
        assessments.add(initial);
        BigDecimal initialRisk = risk(initial.response(), overdue);
        select(
                conditions,
                initial.response(),
                initialRisk,
                originalPayment.get(),
                existing,
                average,
                "ORIGINAL");
        conditions.put("initialPti", conditions.get("pti"));
        conditions.put("initialFinalRiskScore", initialRisk);
        if (initialRisk.compareTo(new BigDecimal("0.15")) <= 0
                && originalPayment.get().compareTo(budget) <= 0
                && amount.compareTo(maxPrincipal) <= 0)
            return result(
                    Kind.APPROVED,
                    "SBA_APPROVED",
                    "Демонстрационное одобрение по модели SBA и финансовым проверкам",
                    conditions,
                    List.of(),
                    null);
        if (initialRisk.compareTo(new BigDecimal("0.35")) > 0)
            return result(
                    Kind.DECLINED,
                    "SBA_RISK_TOO_HIGH",
                    "Индекс риска превышает 0.35",
                    conditions,
                    List.of(),
                    null);
        var policy = product.policy().path("counteroffer");
        if (!policy.isObject() || !policy.path("maxAnnualRatePct").isNumber())
            return result(
                    Kind.REQUEST_INFO,
                    "COUNTEROFFER_POLICY_REQUIRED",
                    "Не настроены ограничения контрпредложения",
                    conditions,
                    List.of("product.counterofferPolicy"),
                    null);
        BigDecimal altRate =
                product.rate()
                        .max(
                                new BigDecimal(context.get().keyRatePct())
                                        .add(new BigDecimal("5"))
                                        .add(new BigDecimal("20").multiply(initialRisk)))
                        .setScale(5, RoundingMode.HALF_UP);
        if (!policy.path("allowed").asBoolean()
                || altRate.compareTo(policy.path("maxAnnualRatePct").decimalValue()) > 0
                || altRate.compareTo(product.rate()) > 0
                        && !Eligibility.contains(policy.path("allowedChanges"), "RATE_INCREASE"))
            return result(
                    Kind.DECLINED,
                    "NO_ACCEPTABLE_COUNTEROFFER",
                    "Допустимое встречное предложение не найдено",
                    conditions,
                    List.of(),
                    null);
        int altTerm = term;
        if (originalPayment.get().compareTo(budget) > 0
                && policy.path("termChangeAllowed").asBoolean()
                && Eligibility.contains(policy.path("allowedChanges"), "TERM_INCREASE"))
            altTerm = Math.min(Math.min(term + 12, product.maxTermMonths()), 360);
        BigDecimal altAmount =
                affordable(product, amount.min(maxPrincipal), altTerm, altRate, budget);
        if (altAmount.compareTo(new BigDecimal(product.minAmount())) < 0
                || altAmount.compareTo(amount) < 0
                        && !Eligibility.contains(policy.path("allowedChanges"), "AMOUNT_DECREASE")
                || altAmount.compareTo(amount) == 0
                        && altTerm == term
                        && altRate.compareTo(product.rate()) == 0)
            return result(
                    Kind.DECLINED,
                    "NO_ACCEPTABLE_COUNTEROFFER",
                    "Допустимое встречное предложение не найдено",
                    conditions,
                    List.of(),
                    null);
        ScoringExchange.Assessment alternative;
        try {
            alternative = assess(answers, product, asOf, altAmount, altTerm, altRate);
        } catch (ScoringGateway.Failure failure) {
            return unavailable(conditions, failure.code);
        }
        assessments.add(alternative);
        var first = initial.response();
        var second = alternative.response();
        if (!first.modelVersion().equals(second.modelVersion())
                || !first.featureVersion().equals(second.featureVersion())
                || !first.calibrationVersion().equals(second.calibrationVersion()))
            return unavailable(conditions, "SCORING_VERSION_CHANGED");
        var altRisk = risk(second, overdue);
        var altPayment = payments.monthly(product, altAmount, altTerm, altRate).orElseThrow();
        conditions.put("alternativeFinalRiskScore", altRisk);
        conditions.put("alternativeMonthlyPayment", altPayment.toPlainString());
        if (altRisk.compareTo(new BigDecimal("0.35")) > 0 || altPayment.compareTo(budget) > 0)
            return result(
                    Kind.DECLINED,
                    "COUNTEROFFER_RISK_TOO_HIGH",
                    "Альтернативные условия не прошли повторную оценку",
                    conditions,
                    List.of(),
                    null);
        select(conditions, second, altRisk, altPayment, existing, average, "ALTERNATIVE");
        return result(
                Kind.COUNTEROFFERED,
                "SBA_COUNTEROFFERED",
                "Демонстрационное контрпредложение: требуется согласие клиента",
                conditions,
                List.of(),
                new Terms(altAmount.toPlainString(), altTerm, altRate.toPlainString()));
    }

    private ScoringExchange.Assessment assess(
            JsonNode answers,
            Catalog.Product product,
            Instant asOf,
            BigDecimal amount,
            int term,
            BigDecimal rate) {
        if (scoring == null) throw new ScoringGateway.Failure("SCORING_UNAVAILABLE");
        var request = ScoringExchange.input(answers, product, asOf, amount, term, rate);
        return new ScoringExchange.Assessment(request, scoring.evaluate(request));
    }

    private BigDecimal risk(ScoringExchange.Output response, BigDecimal overdue) {
        return response.sbaDefaultProbability()
                .add(new BigDecimal("0.50").multiply(overdue))
                .min(BigDecimal.ONE);
    }

    private void select(
            Map<String, Object> conditions,
            ScoringExchange.Output response,
            BigDecimal risk,
            BigDecimal payment,
            BigDecimal existing,
            BigDecimal average,
            String variant) {
        conditions.put("selectedVariant", variant);
        conditions.put("sbaDefaultProbability", response.sbaDefaultProbability());
        conditions.put("finalRiskScore", risk);
        conditions.put("score", response.score());
        conditions.put("modelVersion", response.modelVersion());
        conditions.put("featureVersion", response.featureVersion());
        conditions.put("calibrationVersion", response.calibrationVersion());
        conditions.put("warnings", response.warnings());
        conditions.put("domainStatus", response.domainStatus());
        conditions.put("isDemo", response.isDemo());
        conditions.put("pti", payment.add(existing).divide(average, 12, RoundingMode.HALF_UP));
        conditions.put("totalMonthlyPayment", payment.add(existing).toPlainString());
    }

    private BigDecimal affordable(
            Catalog.Product product,
            BigDecimal upper,
            int term,
            BigDecimal rate,
            BigDecimal budget) {
        BigInteger low = BigInteger.ZERO,
                high = upper.setScale(2, RoundingMode.DOWN).movePointRight(2).toBigIntegerExact();
        while (low.compareTo(high) < 0) {
            var mid = low.add(high).add(BigInteger.ONE).divide(BigInteger.TWO);
            var payment = payments.monthly(product, new BigDecimal(mid, 2), term, rate);
            if (payment.isPresent() && payment.get().compareTo(budget) <= 0) low = mid;
            else high = mid.subtract(BigInteger.ONE);
        }
        return new BigDecimal(low, 2);
    }

    private Review unavailable(Map<String, Object> conditions, String code) {
        conditions.put("scoringErrorCode", code);
        return result(
                Kind.REQUEST_INFO,
                "ASSESSMENT_UNAVAILABLE",
                "Оценка модели недоступна; положительное решение невозможно",
                conditions,
                List.of("scoring"),
                null);
    }

    private Review result(
            Kind kind,
            String code,
            String reason,
            Map<String, Object> conditions,
            List<String> missing,
            Terms terms) {
        conditions.put("policyVersion", VERSION);
        conditions.put("reasonCode", code);
        conditions.put("missingFields", List.copyOf(missing));
        return new Review(kind, reason, conditions, terms);
    }
}
