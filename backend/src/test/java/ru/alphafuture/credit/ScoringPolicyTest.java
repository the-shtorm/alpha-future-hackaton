package ru.alphafuture.credit;

import static org.assertj.core.api.Assertions.*;

import com.fasterxml.jackson.databind.node.ObjectNode;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.*;

/** Границы нового риска, HTTP deadline и повторная оценка финансового контрпредложения. */
class ScoringPolicyTest {
    final ScoringStub stub = new ScoringStub();
    final FormPolicy form = new FormPolicy();
    final Payments payments = new Payments();
    final MacroContext macro = new DataPolicyTest().macro;
    final ScoringGateway gateway = new ScoringGateway(stub.url(), "fixture-key", TestData.JSON);
    final DataPolicy policy =
            new DataPolicy(
                    form,
                    payments,
                    macro,
                    gateway,
                    new LegacyDataPolicy(form, payments, new DemoAssessment(false), macro));
    static final Instant AS_OF = Instant.parse("2026-10-23T10:00:00Z");

    @AfterEach
    void close() {
        stub.close();
    }

    DataPolicy.Review review(ObjectNode input) {
        return policy.review(input, TestData.product(), AS_OF);
    }

    @Test
    void strictBoundariesAndHardRejectBeforeMl() {
        stub.probability = "0.15";
        assertThat(review(TestData.application()).kind()).isEqualTo(DataPolicy.Kind.APPROVED);
        var input = TestData.application();
        ((ObjectNode) input.path("financial")).put("overdue", new BigDecimal("0.20"));
        stub.probability = "0.05";
        assertThat(review(input).kind()).isEqualTo(DataPolicy.Kind.APPROVED);
        int calls = stub.calls.get();
        ((ObjectNode) input.path("financial")).put("overdue", new BigDecimal("0.200000001"));
        assertThat(review(input).kind()).isEqualTo(DataPolicy.Kind.DECLINED);
        assertThat(stub.calls.get()).isEqualTo(calls);
        stub.probability = "0.350000001";
        assertThat(review(TestData.application()).conditions().get("reasonCode"))
                .isEqualTo("SBA_RISK_TOO_HIGH");
    }

    @Test
    void exactPtiBoundaryAndProbabilityScore() {
        var input = TestData.application();
        // Exact payment 96505.99 + debt 0.01 = 0.40 * monthly revenue 241265.
        ((ObjectNode) input.path("financial"))
                .put("revenue", "2895180.00")
                .put("monthlyDebtPayment", "0.01");
        var result = review(input);
        assertThat(result.kind()).isEqualTo(DataPolicy.Kind.APPROVED);
        assertThat((BigDecimal) result.conditions().get("pti")).isEqualByComparingTo("0.40");
        assertThat(ScoringExchange.score(new BigDecimal("0.155"))).isEqualTo(85);
    }

    @Test
    void featureMappingPreservesPercentUnitsAndAgeBoundaries() {
        var input =
                ScoringExchange.input(
                        TestData.application(),
                        TestData.product(),
                        AS_OF,
                        new BigDecimal("1000000"),
                        12,
                        new BigDecimal("28.00000"));
        assertThat(input.loanAmountUsd()).isEqualTo("11111.11");
        assertThat(input.initialInterestRatePct()).isEqualTo("28.00000");
        assertThat(input.naicsCode()).isEqualTo("445110");
        assertThat(input.hasCollateral()).isFalse();
        assertThat(input.businessType()).isEqualTo("CORPORATION");
        long[] months = {0, 11, 12, 23, 24, 35, 36, 47, 48, 59, 60};
        for (long age : months) assertThat(ScoringExchange.ageCategory(age)).isNotBlank();
        assertThat(ScoringExchange.ageCategory(12)).isEqualTo("New Business or 2 years or less");
        assertThat(ScoringExchange.ageCategory(60)).isEqualTo("Existing, 5 or more years");
        assertThatThrownBy(() -> ScoringExchange.ageCategory(-1))
                .isInstanceOf(ScoringGateway.Failure.class);
    }

    ObjectNode burdened() {
        var input = TestData.application();
        ((ObjectNode) input.path("request")).put("amount", "2800000.00");
        ((ObjectNode) input.path("financial"))
                .put("revenue", "6000000.00")
                .put("monthlyDebtPayment", "130000.00");
        return input;
    }

    @Test
    void counterofferUsesAtMostTwoMlCallsAndSelectedRisk() {
        stub.alternativeProbability = "0.12";
        var result = review(burdened());
        assertThat(result.kind()).isEqualTo(DataPolicy.Kind.COUNTEROFFERED);
        assertThat(stub.calls.get()).isEqualTo(2);
        assertThat(result.alternativeTerms().termMonths()).isEqualTo(12);
        assertThat(new BigDecimal(result.alternativeTerms().amount()))
                .isBetween(new BigDecimal("300000"), new BigDecimal("2800000"));
        assertThat(result.conditions().get("selectedVariant")).isEqualTo("ALTERNATIVE");
        assertThat((BigDecimal) result.conditions().get("sbaDefaultProbability"))
                .isEqualByComparingTo("0.12");
        assertThat(stub.authorization).isEqualTo("Bearer fixture-key");
        stub.reset();
        stub.probability = "0.35";
        assertThat(review(burdened()).kind()).isEqualTo(DataPolicy.Kind.COUNTEROFFERED);
        assertThat(stub.calls.get()).isEqualTo(2);
    }

    @Test
    void changedVersionAndFailedAlternativeCannotApprove() {
        stub.switchVersion = true;
        assertThat(review(burdened()).kind()).isEqualTo(DataPolicy.Kind.REQUEST_INFO);
        stub.reset();
        stub.alternativeProbability = "0.36";
        assertThat(review(burdened()).kind()).isEqualTo(DataPolicy.Kind.DECLINED);
    }

    @Test
    void productLimitsAndForbiddenChangesAreRespected() {
        var product = TestData.product();
        ((ObjectNode) product.policy().path("counteroffer")).put("allowed", false);
        assertThat(policy.review(burdened(), product, AS_OF).kind())
                .isEqualTo(DataPolicy.Kind.DECLINED);
        stub.reset();
        product = TestData.product();
        ((ObjectNode) product.policy().path("counteroffer")).put("maxAnnualRatePct", 1);
        assertThat(policy.review(burdened(), product, AS_OF).kind())
                .isEqualTo(DataPolicy.Kind.DECLINED);
        stub.reset();
        var input = burdened();
        ((ObjectNode) input.path("financial")).put("monthlyDebtPayment", "199999.00");
        assertThat(review(input).kind()).isEqualTo(DataPolicy.Kind.DECLINED);
        assertThat(stub.calls.get()).isEqualTo(1);
    }

    @Test
    void faultsAndMalformedResponsesNeverFallBackToDemo() {
        for (int status : new int[] {401, 422, 500, 503}) {
            stub.status = status;
            assertThat(review(TestData.application()).kind())
                    .isEqualTo(DataPolicy.Kind.REQUEST_INFO);
        }
        stub.status = 200;
        for (String body :
                List.of("{}", "{\"sbaDefaultProbability\":NaN}", " ".repeat(65537), "{} {}")) {
            stub.body = body;
            assertThat(review(TestData.application()).kind())
                    .isEqualTo(DataPolicy.Kind.REQUEST_INFO);
        }
    }

    @Test
    void deadlineCoversWholeCall() {
        stub.delay = 2400;
        long start = System.nanoTime();
        assertThat(review(TestData.application()).kind()).isEqualTo(DataPolicy.Kind.REQUEST_INFO);
        assertThat((System.nanoTime() - start) / 1e9).isLessThan(2.3);
    }

    @Test
    void strictGatewayRejectsWrongIdentityScoreAndMetadata() {
        var input =
                ScoringExchange.input(
                        TestData.application(),
                        TestData.product(),
                        AS_OF,
                        new BigDecimal("1000000"),
                        12,
                        new BigDecimal("28"));
        var valid = (ObjectNode) TestData.JSON.tree(gateway.evaluate(input));
        for (String field :
                List.of(
                        "schemaVersion",
                        "requestId",
                        "featureVersion",
                        "modelVersion",
                        "calibrationVersion",
                        "domainStatus")) {
            var bad = valid.deepCopy();
            bad.put(
                    field,
                    Set.of("modelVersion", "calibrationVersion").contains(field) ? "" : "invalid");
            assertThatThrownBy(() -> gateway.validate(bad, input.requestId()))
                    .isInstanceOf(ScoringGateway.Failure.class);
        }
        var wrongScore = valid.deepCopy();
        wrongScore.put("score", 99);
        assertThatThrownBy(() -> gateway.validate(wrongScore, input.requestId()))
                .isInstanceOf(ScoringGateway.Failure.class);
        var bad = valid.deepCopy();
        bad.put("sbaDefaultProbability", new BigDecimal("1.01"));
        var outside = bad;
        assertThatThrownBy(() -> gateway.validate(outside, input.requestId()))
                .isInstanceOf(ScoringGateway.Failure.class);
    }

    @Test
    void alternativeRateIsRoundedOnceToTheFiveDecimalContract() {
        var highMacro =
                new MacroContext(null, null) {
                    @Override
                    Optional<Value> current() {
                        var value = macro.current().orElseThrow();
                        return Optional.of(
                                new Value(
                                        value.id(),
                                        "30.00000",
                                        value.validFrom(),
                                        value.expiresAt(),
                                        value.sourceCode(),
                                        value.recordedAt()));
                    }
                };
        var withHighRate =
                new DataPolicy(
                        form,
                        payments,
                        highMacro,
                        gateway,
                        new LegacyDataPolicy(form, payments, new DemoAssessment(false), highMacro));
        stub.probability = "0.05000012345";
        var result = withHighRate.review(burdened(), TestData.product(), AS_OF);
        assertThat(result.kind()).isEqualTo(DataPolicy.Kind.COUNTEROFFERED);
        assertThat(result.alternativeTerms().annualRatePct()).isEqualTo("36.00000");
        assertThat(stub.calls.get()).isEqualTo(2);
    }

    @Test
    void demonstrationPackageCannotAutomaticallyAssessARealProduct() {
        var p = TestData.product();
        var real =
                new Catalog.Product(
                        p.id(),
                        p.versionId(),
                        p.code(),
                        p.name(),
                        p.currency(),
                        p.minAmount(),
                        p.maxAmount(),
                        p.minTermMonths(),
                        p.maxTermMonths(),
                        p.annualRatePct(),
                        p.borrowerKinds(),
                        p.purposes(),
                        p.policy(),
                        false);
        var result = policy.review(TestData.application(), real, AS_OF);
        assertThat(result.kind()).isEqualTo(DataPolicy.Kind.REQUEST_INFO);
        assertThat(result.conditions().get("reasonCode")).isEqualTo("ASSESSMENT_UNAVAILABLE");
        assertThat(result.conditions().get("scoringErrorCode"))
                .isEqualTo("SBA_DEMO_PRODUCT_REQUIRED");
        assertThat(result.conditions().get("isSimulated")).isEqualTo(false);
        assertThat(stub.calls.get()).isZero();
    }
}
