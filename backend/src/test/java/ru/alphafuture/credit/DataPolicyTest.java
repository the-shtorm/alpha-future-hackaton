package ru.alphafuture.credit;

import static org.assertj.core.api.Assertions.*;

import com.fasterxml.jackson.databind.node.ObjectNode;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.Test;

/** Точные схемы 19/15, платежи и воспроизводимые DEMO-решения по Data Policy 2.1. */
class DataPolicyTest {
    final FormPolicy form = new FormPolicy();
    final Payments payments = new Payments();
    final MacroContext macro =
            new MacroContext(null, null) {
                @Override
                Optional<Value> current() {
                    return Optional.of(
                            new Value(
                                    UUID.fromString("10000000-0000-4000-8000-000000000001"),
                                    "10.00000",
                                    Instant.parse("2026-01-01T00:00:00Z"),
                                    Instant.parse("2027-01-01T00:00:00Z"),
                                    "DEMO_FIXTURE_NOT_CBR",
                                    Instant.parse("2026-01-01T00:00:00Z")));
                }
            };
    final DataPolicy policy = new DataPolicy(form, payments, new DemoAssessment(true), macro);
    static final Instant AS_OF = Instant.parse("2026-10-23T10:00:00Z");

    DataPolicy.Review review(ObjectNode answers) {
        return policy.review(answers, TestData.product(), AS_OF);
    }

    @Test
    void separateSchemasContainNineteenAndFifteenFieldsAndExactlyElevenShared() {
        assertThat(FormPolicy.PRELIMINARY_FIELDS).hasSize(19);
        assertThat(FormPolicy.APPLICATION_FIELDS).hasSize(15);
        assertThat(FormPolicy.TRANSFER_FIELDS).hasSize(11);
        assertThat(FormPolicy.FIELDS).hasSize(23);
        form.validatePreliminary(TestData.preliminary());
        form.validate(TestData.application());
        assertThatThrownBy(() -> form.validate(TestData.preliminary()))
                .isInstanceOf(ApiFailure.class);
        assertThatThrownBy(() -> form.validatePreliminary(TestData.application()))
                .isInstanceOf(ApiFailure.class);
    }

    @Test
    void preliminaryRejectsFutureApplicationDataAndIdentityIsNotInQuestionnaire() {
        for (String payload :
                List.of(
                        "{\"financial\":{\"overdue\":0.1}}",
                        "{\"financial\":{\"monthlyDebtPayment\":\"0.00\"}}",
                        "{\"registration\":{\"taxId\":\"7707083893\"}}"))
            assertThatThrownBy(() -> form.validatePreliminary(TestData.JSON.read(payload)))
                    .isInstanceOf(ApiFailure.class);
        assertThatThrownBy(
                        () -> form.validate(TestData.JSON.read("{\"financial\":{\"monthly\":[]}}")))
                .isInstanceOf(ApiFailure.class);
    }

    @Test
    void knownZeroAndFalseAreDifferentFromMissingAndInvalid() {
        var answers = TestData.application();
        assertThat(form.statuses(answers).get("financial.monthlyDebtPayment"))
                .isEqualTo(FormPolicy.ValueStatus.KNOWN);
        assertThat(form.statuses(answers).get("business.mspRegistry"))
                .isEqualTo(FormPolicy.ValueStatus.KNOWN);
        ((ObjectNode) answers.path("financial")).remove("monthlyDebtPayment");
        assertThat(form.statuses(answers).get("financial.monthlyDebtPayment"))
                .isEqualTo(FormPolicy.ValueStatus.UNKNOWN);
        assertThat(review(answers).kind()).isEqualTo(DataPolicy.Kind.REQUEST_INFO);
        ((ObjectNode) answers.path("financial")).put("revenue", "-1.00");
        assertThat(form.statuses(answers).get("financial.revenue"))
                .isEqualTo(FormPolicy.ValueStatus.INVALID);
    }

    @Test
    void overdueHardRejectHasNoCounterofferAndUsesExactBoundary() {
        var a = TestData.application();
        ((ObjectNode) a.path("financial")).put("overdue", new BigDecimal("0.2"));
        assertThat(review(a).kind()).isNotEqualTo(DataPolicy.Kind.DECLINED);
        ((ObjectNode) a.path("financial")).put("overdue", new BigDecimal("0.200000000001"));
        var rejected = review(a);
        assertThat(rejected.kind()).isEqualTo(DataPolicy.Kind.DECLINED);
        assertThat(rejected.alternativeTerms()).isNull();
        assertThat(rejected.conditions().get("counterofferAllowed")).isEqualTo(false);
        ((ObjectNode) a.path("financial")).put("overdue", true);
        assertThatThrownBy(() -> form.validate(a)).isInstanceOf(ApiFailure.class);
    }

    @Test
    void zeroRevenueAndNonFullPeriodsRequestInformation() {
        var a = TestData.application();
        ((ObjectNode) a.path("financial")).put("revenue", "0.00");
        assertThat(review(a).conditions().get("missingFields"))
                .isEqualTo(List.of("financial.revenue"));
        ((ObjectNode) a.path("financial")).put("revenue", "1.00").put("periodFrom", "2025-10-02");
        assertThat(review(a).kind()).isEqualTo(DataPolicy.Kind.REQUEST_INFO);
    }

    @Test
    void exactAnnuityMatchesZeroRateAndKnownPaymentAndRejectsUnknownSchedules() {
        var product = TestData.product();
        assertThat(
                        payments.monthly(product, new BigDecimal("1200"), 12, BigDecimal.ZERO)
                                .orElseThrow())
                .isEqualByComparingTo("100.00");
        assertThat(
                        payments.monthly(
                                        product,
                                        new BigDecimal("1000000"),
                                        12,
                                        new BigDecimal("28"))
                                .orElseThrow())
                .isEqualByComparingTo("96505.99");
        ((ObjectNode) product.policy()).put("repayment", "FACILITY_SPECIFIC_SCHEDULE");
        assertThat(payments.monthly(product, BigDecimal.TEN, 12, BigDecimal.ONE)).isEmpty();
        assertThat(
                        policy.review(TestData.application(), product, AS_OF)
                                .conditions()
                                .get("missingFields"))
                .isEqualTo(List.of("product.paymentSchedule"));
    }

    @Test
    void fullDebtBudgetCannotBeFixedByReducingNewAmount() {
        var a = TestData.application();
        ((ObjectNode) a.path("financial")).put("monthlyDebtPayment", "800000.00");
        assertThat(review(a).kind()).isEqualTo(DataPolicy.Kind.DECLINED);
        ((ObjectNode) a.path("financial")).put("monthlyDebtPayment", "800000.01");
        assertThat(review(a).kind()).isEqualTo(DataPolicy.Kind.DECLINED);
    }

    @Test
    void counterofferChangesOnlyAmountAndRateAndFitsTotalPaymentBudget() {
        var a = TestData.application();
        ((ObjectNode) a.path("request")).put("amount", "2800000.00");
        ((ObjectNode) a.path("financial"))
                .put("revenue", "6000000.00")
                .put("monthlyDebtPayment", "130000.00");
        var original = a.deepCopy();
        var r = review(a);
        assertThat(r.kind()).isEqualTo(DataPolicy.Kind.COUNTEROFFERED);
        assertThat(a).isEqualTo(original);
        assertThat(r.alternativeTerms().termMonths()).isEqualTo(12);
        assertThat(new BigDecimal(r.alternativeTerms().amount()))
                .isGreaterThan(new BigDecimal("300000"))
                .isLessThan(new BigDecimal("2800000"));
        assertThat(new BigDecimal(r.alternativeTerms().annualRatePct()))
                .isGreaterThan(new BigDecimal("28"));
        assertThat(new BigDecimal(r.conditions().get("totalMonthlyPayment").toString()))
                .isLessThanOrEqualTo(new BigDecimal("200000"));
        var assessment = (DemoAssessment.Value) r.conditions().get("alternativeAssessment");
        assertThat(new BigDecimal(r.alternativeTerms().annualRatePct()))
                .isEqualByComparingTo(
                        new BigDecimal("10").add(new BigDecimal(assessment.riskMarginPct())));
    }

    @Test
    void deterministicDemoAssessmentIsExplicitAndDisabledForRealProducts() {
        var demo = new DemoAssessment(true);
        var a =
                demo.calculate(
                        new BigDecimal("0.1"), new BigDecimal("0.05"), new BigDecimal("2"), 24);
        var b =
                demo.calculate(
                        new BigDecimal("0.1"), new BigDecimal("0.05"), new BigDecimal("2"), 24);
        assertThat(a).isEqualTo(b);
        assertThat(a.mode()).isEqualTo("DEMO");
        var result =
                new DataPolicy(form, payments, new DemoAssessment(false), macro)
                        .review(TestData.application(), TestData.product(), AS_OF);
        assertThat(result.kind()).isEqualTo(DataPolicy.Kind.REQUEST_INFO);
        assertThat(result.conditions().get("missingFields")).isEqualTo(List.of("scoring"));
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
        assertThat(demo.enabled(real)).isFalse();
    }

    @Test
    void absentMacroNeverFabricatesAKeyRate() {
        var absent =
                new MacroContext(null, null) {
                    @Override
                    Optional<Value> current() {
                        return Optional.empty();
                    }
                };
        var r =
                new DataPolicy(form, payments, new DemoAssessment(true), absent)
                        .review(TestData.application(), TestData.product(), AS_OF);
        assertThat(r.kind()).isEqualTo(DataPolicy.Kind.REQUEST_INFO);
        assertThat(r.conditions().get("missingFields"))
                .isEqualTo(List.of("macroeconomic.key_rate_pct"));
    }

    @Test
    void transferProjectionExcludesEightSelectionOnlyFieldsAndPreservesMoney() {
        var preliminary = TestData.preliminary();
        ((ObjectNode) preliminary.path("request")).put("amount", "1000000.01");
        var transferred = FormPolicy.project(preliminary, FormPolicy.TRANSFER_FIELDS);
        assertThat(transferred.path("business").has("sector")).isFalse();
        assertThat(transferred.path("registration").has("country")).isFalse();
        assertThat(FormPolicy.money(transferred, "request.amount"))
                .isEqualByComparingTo("1000000.01");
        assertThat(FormPolicy.project(transferred, FormPolicy.TRANSFER_FIELDS))
                .isEqualTo(transferred);
    }

    @Test
    void percentDatesAndCanonicalSnapshotRemainStable() {
        var a = TestData.application();
        ((ObjectNode) a.path("project")).put("ownContributionPct", "20.00");
        var c = review(a).conditions();
        assertThat(c.get("ownContributionShare")).isEqualTo("0.2000");
        assertThat(c.get("registeredAgeMonths")).isEqualTo(81L);
        assertThat(TestData.JSON.canonical(TestData.JSON.read("{\"b\":1,\"a\":2}")))
                .isEqualTo("{\"a\":2,\"b\":1}");
    }
}
