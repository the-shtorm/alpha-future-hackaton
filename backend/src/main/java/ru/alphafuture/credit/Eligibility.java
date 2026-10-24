package ru.alphafuture.credit;

import com.fasterxml.jackson.databind.JsonNode;
import java.math.*;
import java.time.*;
import java.time.temporal.ChronoUnit;
import java.util.*;
import org.springframework.stereotype.Component;

/** Проверяет применимость продукта по предварительной форме, не принимает кредитных решений. */
@Component
class Eligibility {
    static final String VERSION = "eligibility-3.0";

    enum Status {
        ELIGIBLE,
        CONDITIONAL,
        INELIGIBLE
    }

    enum Outcome {
        PASS,
        FAIL,
        UNKNOWN,
        REVIEW
    }

    record Reason(
            String code,
            String field,
            Outcome result,
            String message,
            Object actual,
            Object expected) {}

    record Result(UUID productVersionId, String productCode, Status status, List<Reason> reasons) {
        List<String> missingFields() {
            return reasons.stream()
                    .filter(r -> r.result() == Outcome.UNKNOWN)
                    .map(Reason::field)
                    .distinct()
                    .toList();
        }
    }

    Result evaluate(Catalog.Product product, JsonNode answers, Instant asOf) {
        var checks = new ArrayList<Reason>();
        var rules = product.policy().path("eligibility");
        range(
                checks,
                answers,
                "request.amount",
                new BigDecimal(product.minAmount()),
                new BigDecimal(product.maxAmount()),
                "AMOUNT_OUT_OF_RANGE",
                "Сумма должна быть в диапазоне продукта");
        range(
                checks,
                answers,
                "request.termMonths",
                BigDecimal.valueOf(product.minTermMonths()),
                BigDecimal.valueOf(product.maxTermMonths()),
                "TERM_OUT_OF_RANGE",
                "Срок должен быть в диапазоне продукта");
        allowed(
                checks,
                answers,
                "request.purpose",
                product.purposes(),
                "PURPOSE_NOT_SUPPORTED",
                "Цель должна поддерживаться продуктом");
        allowed(
                checks,
                answers,
                "registration.borrowerKind",
                product.borrowerKinds(),
                "BORROWER_KIND_NOT_SUPPORTED",
                "Форма бизнеса должна поддерживаться продуктом");
        String usage = FormPolicy.text(answers, "request.usageMode");
        if (usage != null && !usage.equals("UNKNOWN"))
            add(
                    checks,
                    "USAGE_MODE_NOT_SUPPORTED",
                    "request.usageMode",
                    product.usageModes().isEmpty()
                            ? Outcome.UNKNOWN
                            : product.usageModes().contains(usage) ? Outcome.PASS : Outcome.FAIL,
                    "Проверка способа использования средств",
                    usage,
                    product.usageModes());
        var excluded = product.policy().path("common_policy").path("excluded_sectors");
        String sector = FormPolicy.text(answers, "business.sector");
        add(
                checks,
                "SECTOR_EXCLUDED",
                "business.sector",
                sector == null || sector.equals("UNKNOWN")
                        ? Outcome.UNKNOWN
                        : contains(excluded, sector) ? Outcome.FAIL : Outcome.PASS,
                "Проверка отраслевых исключений",
                sector,
                excluded);
        if (rules.path("tax_regimes").isArray())
            allowed(
                    checks,
                    answers,
                    "business.taxRegime",
                    rules.path("tax_regimes"),
                    "TAX_REGIME_NOT_SUPPORTED",
                    "Налоговый режим должен поддерживаться продуктом");
        long minAge = rules.path("min_business_age_months").asLong();
        LocalDate started = FormPolicy.date(answers, "business.actualStartedOn");
        Long operatingMonths =
                started == null
                        ? null
                        : ChronoUnit.MONTHS.between(
                                started, asOf.atZone(ZoneOffset.UTC).toLocalDate());
        add(
                checks,
                "BUSINESS_AGE_TOO_SHORT",
                "business.actualStartedOn",
                operatingMonths == null
                        ? Outcome.UNKNOWN
                        : operatingMonths < minAge ? Outcome.FAIL : Outcome.PASS,
                "Проверка минимального стажа",
                operatingMonths,
                minAge);
        Long months = periodMonths(answers);
        BigDecimal revenue = FormPolicy.money(answers, "financial.revenue");
        BigDecimal average =
                months == null || revenue == null
                        ? null
                        : revenue.divide(BigDecimal.valueOf(months), 12, RoundingMode.HALF_UP);
        BigDecimal minRevenue = rules.path("min_average_monthly_revenue_rub").decimalValue();
        boolean enough =
                months != null
                        && revenue != null
                        && revenue.compareTo(minRevenue.multiply(BigDecimal.valueOf(months))) >= 0;
        add(
                checks,
                "REVENUE_BELOW_MINIMUM",
                "financial.revenue",
                average == null ? Outcome.UNKNOWN : enough ? Outcome.PASS : Outcome.FAIL,
                "Проверка среднемесячной выручки",
                average,
                minRevenue);
        int window = rules.path("revenue_window_months").asInt();
        add(
                checks,
                "REVENUE_HISTORY_INCOMPLETE",
                "financial.periodFrom",
                months == null ? Outcome.UNKNOWN : months < window ? Outcome.REVIEW : Outcome.PASS,
                "Проверка полноты истории выручки",
                months,
                window);
        if (product.policy().path("collateral").path("required").asBoolean())
            ready(
                    checks,
                    answers,
                    "security.collateralReady",
                    "COLLATERAL_REQUIRED",
                    "Нужна готовность предоставить обеспечение");
        String borrower = FormPolicy.text(answers, "registration.borrowerKind");
        if (borrower != null
                && product.policy().path("guarantor").path(borrower).asText().endsWith("_REQUIRED"))
            ready(
                    checks,
                    answers,
                    "security.guarantorReady",
                    "GUARANTOR_REQUIRED",
                    "Нужна готовность привлечь поручителя");
        for (var extra : rules.path("extra_conditions"))
            switch (extra.asText()) {
                case "DEMO_BANK_ACCOUNT_6_MONTHS", "MARKETPLACE_6_MONTHS" ->
                        add(
                                checks,
                                "ADDITIONAL_CONDITION_REQUIRES_REVIEW",
                                "product.additionalConditions",
                                Outcome.REVIEW,
                                "Дополнительное условие продукта проверяется отдельно",
                                null,
                                extra.asText());
                case "MSP_REGISTRY" ->
                        ready(
                                checks,
                                answers,
                                "business.mspRegistry",
                                "MSP_REQUIRED",
                                "Нужно членство в реестре МСП");
                case "MANUFACTURING" ->
                        equal(
                                checks,
                                answers,
                                "business.sector",
                                "MANUFACTURING",
                                "SECTOR_NOT_SUPPORTED",
                                "Продукт предназначен для производства");
                default -> {
                    /* Документы проверяются по полной заявке, не по короткой форме. */
                }
            }
        Status status =
                checks.stream().anyMatch(r -> r.result() == Outcome.FAIL)
                        ? Status.INELIGIBLE
                        : checks.stream()
                                        .anyMatch(
                                                r ->
                                                        r.result() == Outcome.UNKNOWN
                                                                || r.result() == Outcome.REVIEW)
                                ? Status.CONDITIONAL
                                : Status.ELIGIBLE;
        return new Result(product.versionId(), product.code(), status, List.copyOf(checks));
    }

    static Long periodMonths(JsonNode answers) {
        LocalDate from = FormPolicy.date(answers, "financial.periodFrom"),
                to = FormPolicy.date(answers, "financial.periodTo");
        if (from == null
                || to == null
                || from.getDayOfMonth() != 1
                || to.getDayOfMonth() != to.lengthOfMonth()) return null;
        long months = ChronoUnit.MONTHS.between(from, to.plusDays(1));
        return months > 0 ? months : null;
    }

    static boolean contains(JsonNode values, String value) {
        for (var item : values) if (item.asText().equals(value)) return true;
        return false;
    }

    private void add(
            List<Reason> list,
            String code,
            String field,
            Outcome result,
            String message,
            Object actual,
            Object expected) {
        list.add(new Reason(code, field, result, message, actual, expected));
    }

    private void range(
            List<Reason> list,
            JsonNode answers,
            String field,
            BigDecimal min,
            BigDecimal max,
            String code,
            String text) {
        BigDecimal actual = FormPolicy.money(answers, field);
        add(
                list,
                code,
                field,
                actual == null
                        ? Outcome.UNKNOWN
                        : actual.compareTo(min) < 0 || actual.compareTo(max) > 0
                                ? Outcome.FAIL
                                : Outcome.PASS,
                text,
                actual,
                Map.of("min", min, "max", max));
    }

    private void equal(
            List<Reason> list,
            JsonNode answers,
            String field,
            String expected,
            String code,
            String text) {
        String actual = FormPolicy.text(answers, field);
        add(
                list,
                code,
                field,
                actual == null || actual.equals("UNKNOWN")
                        ? Outcome.UNKNOWN
                        : actual.equals(expected) ? Outcome.PASS : Outcome.FAIL,
                text,
                actual,
                expected);
    }

    private void allowed(
            List<Reason> list,
            JsonNode answers,
            String field,
            JsonNode expected,
            String code,
            String text) {
        String actual = FormPolicy.text(answers, field);
        add(
                list,
                code,
                field,
                actual == null || actual.equals("UNKNOWN")
                        ? Outcome.UNKNOWN
                        : contains(expected, actual) ? Outcome.PASS : Outcome.FAIL,
                text,
                actual,
                expected);
    }

    private void ready(
            List<Reason> list, JsonNode answers, String field, String code, String text) {
        var actual = FormPolicy.value(answers, field);
        add(
                list,
                code,
                field,
                actual.isBoolean()
                        ? actual.asBoolean() ? Outcome.PASS : Outcome.FAIL
                        : switch (actual.asText()) {
                            case "YES" -> Outcome.PASS;
                            case "NO" -> Outcome.FAIL;
                            case "DISCUSS" -> Outcome.REVIEW;
                            default -> Outcome.UNKNOWN;
                        },
                text,
                actual.isMissingNode() || actual.isNull() ? null : actual,
                field.equals("business.mspRegistry") ? true : "YES");
    }
}
