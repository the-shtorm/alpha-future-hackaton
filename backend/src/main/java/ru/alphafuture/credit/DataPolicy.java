package ru.alphafuture.credit;

import com.fasterxml.jackson.databind.JsonNode;
import java.math.*;
import java.time.*;
import java.time.temporal.ChronoUnit;
import java.util.*;
import org.springframework.stereotype.Component;

/** Политика 2.1: проверяемые ограничения, платежный бюджет и явно маркированный DEMO-маршрут. */
@Component
class DataPolicy {
    static final String VERSION = "data-policy-2.1";

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
    private final DemoAssessment demo;
    private final MacroContext macro;

    DataPolicy(FormPolicy form, Payments payments, DemoAssessment demo, MacroContext macro) {
        this.form = form;
        this.payments = payments;
        this.demo = demo;
        this.macro = macro;
    }

    Review review(JsonNode answers, Catalog.Product product, Instant asOf) {
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
        if (!demo.enabled(product)) {
            conditions.put("mode", "UNAVAILABLE");
            return result(
                    Kind.REQUEST_INFO,
                    "ASSESSMENT_UNAVAILABLE",
                    "Оценка сделки не подключена",
                    conditions,
                    List.of("scoring"),
                    null);
        }
        var context = macro.current();
        if (context.isEmpty())
            return result(
                    Kind.REQUEST_INFO,
                    "MACRO_CONTEXT_REQUIRED",
                    "Не задан действующий серверный макроконтекст",
                    conditions,
                    List.of("macroeconomic.key_rate_pct"),
                    null);
        conditions.put("macroeconomic", context.get());
        conditions.put("key_rate_pct", context.get().keyRatePct());
        conditions.put("mode", "DEMO");
        conditions.put("isSimulated", true);
        var initial = demo.calculate(debtRatio, overdue, amountRatio, age);
        conditions.put("assessment", initial);
        if (originalPayment.get().compareTo(budget) <= 0
                && amount.compareTo(maxPrincipal) <= 0
                && new BigDecimal(initial.score()).compareTo(DemoAssessment.THRESHOLD) >= 0)
            return result(
                    Kind.APPROVED,
                    "DEMO_APPROVED",
                    "Одобрено временными DEMO-правилами; это не результат обученной модели",
                    conditions,
                    List.of(),
                    null);
        if (!product.policy().path("counteroffer").path("allowed").asBoolean()
                || !Eligibility.contains(
                        product.policy().path("counteroffer").path("allowedChanges"),
                        "AMOUNT_DECREASE")
                || !Eligibility.contains(
                        product.policy().path("counteroffer").path("allowedChanges"),
                        "RATE_INCREASE")
                || !product.policy().path("counteroffer").path("maxAnnualRatePct").isNumber())
            return result(
                    Kind.REQUEST_INFO,
                    "COUNTEROFFER_POLICY_REQUIRED",
                    "Продукт не разрешает автоматически рассчитывать альтернативные условия",
                    conditions,
                    List.of("product.counterofferPolicy"),
                    null);
        var alternative =
                alternative(
                        product,
                        amount.min(maxPrincipal),
                        term,
                        budget,
                        debtRatio,
                        overdue,
                        revenue,
                        monthCount,
                        age,
                        new BigDecimal(context.get().keyRatePct()));
        if (alternative.isEmpty())
            return result(
                    Kind.DECLINED,
                    "NO_ACCEPTABLE_COUNTEROFFER",
                    "В допустимых границах продукта встречное предложение не найдено",
                    conditions,
                    List.of(),
                    null);
        var terms = alternative.get();
        BigDecimal selected = new BigDecimal(terms.amount());
        var selectedAssessment =
                demo.calculate(
                        debtRatio,
                        overdue,
                        selected.multiply(monthCount).divide(revenue, 12, RoundingMode.HALF_UP),
                        age);
        var payment =
                payments.monthly(product, selected, term, new BigDecimal(terms.annualRatePct()))
                        .orElseThrow();
        conditions.put("alternativeAssessment", selectedAssessment);
        conditions.put("totalMonthlyPayment", payment.add(existing).toPlainString());
        conditions.put("alternativeMonthlyPayment", payment.toPlainString());
        conditions.put("macroContextId", context.get().id());
        return result(
                Kind.COUNTEROFFERED,
                "DEMO_COUNTEROFFERED",
                "DEMO: доступны меньшая сумма и повышенная ставка; требуется согласие клиента",
                conditions,
                List.of(),
                terms);
    }

    private Optional<Terms> alternative(
            Catalog.Product product,
            BigDecimal upper,
            int term,
            BigDecimal budget,
            BigDecimal debt,
            BigDecimal overdue,
            BigDecimal revenue,
            BigDecimal months,
            long age,
            BigDecimal keyRate) {
        BigInteger low = BigInteger.ZERO,
                high =
                        upper.subtract(new BigDecimal("0.01"))
                                .max(BigDecimal.ZERO)
                                .setScale(2, RoundingMode.DOWN)
                                .movePointRight(2)
                                .toBigIntegerExact();
        BigDecimal cap =
                product.policy().path("counteroffer").path("maxAnnualRatePct").decimalValue();
        while (low.compareTo(high) < 0) {
            var mid = low.add(high).add(BigInteger.ONE).divide(BigInteger.TWO);
            BigDecimal amount = new BigDecimal(mid, 2);
            var assessment =
                    demo.calculate(
                            debt,
                            overdue,
                            amount.multiply(months).divide(revenue, 12, RoundingMode.HALF_UP),
                            age);
            BigDecimal rate = keyRate.add(new BigDecimal(assessment.riskMarginPct()));
            var payment = payments.monthly(product, amount, term, rate);
            boolean valid =
                    new BigDecimal(assessment.score()).compareTo(DemoAssessment.THRESHOLD) >= 0
                            && rate.compareTo(cap) <= 0
                            && payment.isPresent()
                            && payment.get().compareTo(budget) <= 0;
            if (valid) low = mid;
            else high = mid.subtract(BigInteger.ONE);
        }
        BigDecimal amount = new BigDecimal(low, 2);
        if (amount.compareTo(new BigDecimal(product.minAmount())) <= 0) return Optional.empty();
        var assessment =
                demo.calculate(
                        debt,
                        overdue,
                        amount.multiply(months).divide(revenue, 12, RoundingMode.HALF_UP),
                        age);
        BigDecimal rate = keyRate.add(new BigDecimal(assessment.riskMarginPct()));
        if (rate.compareTo(product.rate()) <= 0) return Optional.empty();
        return Optional.of(new Terms(amount.toPlainString(), term, rate.toPlainString()));
    }

    private Review result(
            Kind kind,
            String reasonCode,
            String reason,
            Map<String, Object> conditions,
            List<String> missing,
            Terms alternative) {
        conditions.put("policyVersion", VERSION);
        conditions.put("reasonCode", reasonCode);
        conditions.put("missingFields", List.copyOf(missing));
        return new Review(kind, reason, conditions, alternative);
    }
}
