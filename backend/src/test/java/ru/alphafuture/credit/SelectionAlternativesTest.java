package ru.alphafuture.credit;

import static org.assertj.core.api.Assertions.*;

import com.fasterxml.jackson.databind.node.ObjectNode;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.Test;

class SelectionAlternativesTest {
    final SelectionAlternatives engine =
            new SelectionAlternatives(new Eligibility(), TestData.JSON);
    final Instant asOf = Instant.parse("2026-10-26T10:00:00Z");

    ObjectNode equipment() {
        var answers = TestData.preliminary();
        ((ObjectNode) answers.path("request"))
                .put("purpose", "EQUIPMENT")
                .put("amount", "2000000.00");
        ((ObjectNode) answers.path("financial"))
                .put("revenue", "2000000.00")
                .put("periodFrom", "2026-04-01")
                .put("periodTo", "2026-06-30");
        return answers;
    }

    @Test
    void equipmentCanUseBroadDevelopmentPurposeWithoutChangingBusinessFacts() {
        var answers = equipment();
        var before = answers.deepCopy();
        var options = engine.suggest(List.of(TestData.product()), answers, asOf);
        assertThat(options).hasSize(1);
        var option = options.getFirst();
        assertThat(option.answersPatch())
                .isEqualTo(TestData.JSON.read("{\"request\":{\"purpose\":\"DEVELOPMENT\"}}"));
        assertThat(option.eligibility().status()).isEqualTo(Eligibility.Status.CONDITIONAL);
        assertThat(option.eligibility().reasons())
                .anyMatch(
                        r ->
                                r.code().equals("REVENUE_HISTORY_INCOMPLETE")
                                        && r.result() == Eligibility.Outcome.REVIEW);
        assertThat(answers).isEqualTo(before);
    }

    @Test
    void outOfRangeAmountAndTermProduceConcreteNearestTerms() {
        var answers = TestData.preliminary();
        ((ObjectNode) answers.path("request")).put("amount", "99000000.00").put("termMonths", 60);
        var option = engine.suggest(List.of(TestData.product()), answers, asOf).getFirst();
        assertThat(option.answersPatch().path("request").path("amount").asText())
                .isEqualTo("3000000.00");
        assertThat(option.answersPatch().path("request").path("termMonths").asInt()).isEqualTo(24);
        assertThat(option.changes())
                .extracting(SelectionAlternatives.Change::field)
                .containsExactly("request.amount", "request.termMonths");
    }

    @Test
    void neverInventsRevenueAgeTaxRegimeSectorOrSecurity() {
        for (String field : List.of("revenue", "age", "tax", "sector", "guarantor", "collateral")) {
            var answers = equipment();
            var product = TestData.product();
            switch (field) {
                case "revenue" -> ((ObjectNode) answers.path("financial")).put("revenue", "10.00");
                case "age" ->
                        ((ObjectNode) answers.path("business"))
                                .put("actualStartedOn", "2026-10-01");
                case "tax" -> ((ObjectNode) answers.path("business")).put("taxRegime", "NPD");
                case "sector" -> ((ObjectNode) answers.path("business")).put("sector", "GAMBLING");
                case "guarantor" ->
                        ((ObjectNode) answers.path("security")).put("guarantorReady", "NO");
                case "collateral" ->
                        ((ObjectNode) product.policy().path("collateral")).put("required", true);
            }
            assertThat(engine.suggest(List.of(product), answers, asOf)).as(field).isEmpty();
        }
    }

    @Test
    void doesNotSubstituteUnrelatedPurposesOrIncreaseTheRequestedAmount() {
        var answers = equipment();
        ((ObjectNode) answers.path("request")).put("purpose", "REFINANCING");
        assertThat(engine.suggest(List.of(TestData.product()), answers, asOf)).isEmpty();
        answers = equipment();
        ((ObjectNode) answers.path("request")).put("amount", "10000.00");
        assertThat(engine.suggest(List.of(TestData.product()), answers, asOf)).isEmpty();
    }

    @Test
    void offersUsageChangeExplicitlyAndPreservesUnknownRevenueAsUnknown() {
        var answers = TestData.preliminary();
        ((ObjectNode) answers.path("request")).put("usageMode", "IN_PARTS");
        ((ObjectNode) answers.path("financial")).putNull("revenue");
        var option = engine.suggest(List.of(TestData.product()), answers, asOf).getFirst();
        assertThat(option.changes())
                .extracting(SelectionAlternatives.Change::field)
                .containsExactly("request.usageMode");
        assertThat(option.eligibility().missingFields()).contains("financial.revenue");
        assertThat(option.answersPatch().has("financial")).isFalse();
    }

    @Test
    void limitsAlternativesAndDoesNotDistractFromAnExistingMatch() {
        var products =
                java.util.stream.IntStream.range(0, 5).mapToObj(i -> TestData.product()).toList();
        assertThat(engine.suggest(products, equipment(), asOf)).hasSize(3);
        assertThat(engine.suggest(products, TestData.preliminary(), asOf)).isEmpty();
    }
}
