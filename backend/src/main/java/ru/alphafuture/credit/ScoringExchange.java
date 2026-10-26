package ru.alphafuture.credit;

import com.fasterxml.jackson.databind.JsonNode;
import java.math.*;
import java.time.*;
import java.time.temporal.ChronoUnit;
import java.util.*;

/** Версионированные девять признаков SBA и подтверждённый ответ модели. */
class ScoringExchange {
    static final String SCHEMA = "sba-scoring-1";
    static final BigDecimal FX = new BigDecimal("90.00");
    static final Map<String, String> NAICS =
            Map.of(
                    "TRADE",
                    "445110",
                    "MANUFACTURING",
                    "332710",
                    "SERVICES",
                    "811111",
                    "IT",
                    "541511",
                    "CONSTRUCTION",
                    "236220",
                    "AGRICULTURE",
                    "111998",
                    "LOGISTICS",
                    "484110",
                    "TRANSPORT",
                    "484110");

    record Input(
            String schemaVersion,
            UUID requestId,
            String loanAmountUsd,
            int termMonths,
            String initialInterestRatePct,
            String interestRateType,
            boolean isRevolving,
            boolean hasCollateral,
            String businessType,
            String businessAgeCategory,
            String naicsCode) {}

    record Output(
            String schemaVersion,
            UUID requestId,
            BigDecimal sbaDefaultProbability,
            int score,
            String modelVersion,
            String featureVersion,
            String calibrationVersion,
            String domainStatus,
            boolean isDemo,
            List<String> warnings) {}

    record Assessment(Input request, Output response) {}

    static Input input(
            JsonNode answers,
            Catalog.Product product,
            Instant asOf,
            BigDecimal amount,
            int term,
            BigDecimal rate) {
        String kind =
                switch (Objects.toString(
                        FormPolicy.text(answers, "registration.borrowerKind"), "")) {
                    case "LLC" -> "CORPORATION";
                    case "IP" -> "INDIVIDUAL";
                    default -> throw new ScoringGateway.Failure("SCORING_MAPPING_REQUIRED");
                };
        String naics = NAICS.get(FormPolicy.text(answers, "business.sector"));
        String rateType = product.policy().path("pricing").path("rate_type").asText();
        if (naics == null
                || product.type() == null
                || !Set.of("FIXED", "VARIABLE").contains(rateType)
                || term < 1
                || term > 360) throw new ScoringGateway.Failure("SCORING_MAPPING_REQUIRED");
        long months =
                ChronoUnit.MONTHS.between(
                        FormPolicy.date(answers, "business.actualStartedOn"),
                        asOf.atZone(ZoneOffset.UTC).toLocalDate());
        BigDecimal value = FormPolicy.money(answers, "security.collateralValue");
        BigDecimal usd = amount.divide(FX, 2, RoundingMode.HALF_UP);
        if (usd.signum() <= 0 || rate.signum() < 0 || rate.scale() > 5)
            throw new ScoringGateway.Failure("SCORING_MAPPING_REQUIRED");
        return new Input(
                SCHEMA,
                UUID.randomUUID(),
                usd.toPlainString(),
                term,
                rate.toPlainString(),
                rateType,
                Set.of("REVOLVING_CREDIT_LINE", "OVERDRAFT").contains(product.type()),
                "YES".equals(FormPolicy.text(answers, "security.collateralReady"))
                        && value != null
                        && value.signum() > 0,
                kind,
                ageCategory(months),
                naics);
    }

    static String ageCategory(long months) {
        if (months < 0) throw new ScoringGateway.Failure("SCORING_MAPPING_REQUIRED");
        if (months < 12) return "New, Less than 1 Year old";
        if (months < 24) return "New Business or 2 years or less";
        if (months < 36) return "Less than 3 years old but at least 2";
        if (months < 48) return "Less than 4 years old but at least 3";
        if (months < 60) return "Less than 5 years old but at least 4";
        return "Existing, 5 or more years";
    }

    static int score(BigDecimal probability) {
        return BigDecimal.ONE
                .subtract(probability)
                .multiply(new BigDecimal("100"))
                .setScale(0, RoundingMode.HALF_UP)
                .intValueExact();
    }
}
