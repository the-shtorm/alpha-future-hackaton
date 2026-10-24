package ru.alphafuture.credit;

import static org.assertj.core.api.Assertions.*;

import com.fasterxml.jackson.databind.node.ObjectNode;
import java.time.Instant;
import org.junit.jupiter.api.Test;

/** Раздельные правила применимости, причины и отсутствие банковского скоринга в форме. */
class EligibilityTest {
    final Eligibility engine = new Eligibility();
    final Instant asOf = Instant.parse("2026-10-23T10:00:00Z");

    @Test
    void completeMatchingFormIsEligibleWithMachineReadableReasons() {
        var result = engine.evaluate(TestData.product(), TestData.preliminary(), asOf);
        assertThat(result.status()).isEqualTo(Eligibility.Status.ELIGIBLE);
        assertThat(result.reasons())
                .allSatisfy(
                        reason -> {
                            assertThat(reason.code()).isNotBlank();
                            assertThat(reason.message()).isNotBlank();
                            assertThat(reason.field()).isNotBlank();
                        });
    }

    @Test
    void unknownRevenueIsConditionalRatherThanZeroOrRejection() {
        var a = TestData.preliminary();
        ((ObjectNode) a.path("financial")).remove("revenue");
        var r = engine.evaluate(TestData.product(), a, asOf);
        assertThat(r.status()).isEqualTo(Eligibility.Status.CONDITIONAL);
        assertThat(r.missingFields()).contains("financial.revenue");
    }

    @Test
    void amountAndPurposeFailuresAreExplicit() {
        var a = TestData.preliminary();
        ((ObjectNode) a.path("request"))
                .put("amount", "99999999999999.00")
                .put("purpose", "REFINANCING");
        var r = engine.evaluate(TestData.product(), a, asOf);
        assertThat(r.status()).isEqualTo(Eligibility.Status.INELIGIBLE);
        assertThat(r.reasons())
                .anySatisfy(
                        reason -> {
                            assertThat(reason.code()).isEqualTo("AMOUNT_OUT_OF_RANGE");
                            assertThat(reason.result()).isEqualTo(Eligibility.Outcome.FAIL);
                        });
    }

    @Test
    void collateralFalseAndMissingAreDifferentAndDoNotConfirmAnAsset() {
        var p = TestData.product();
        ((ObjectNode) p.policy().path("collateral")).put("required", true);
        var a = TestData.preliminary();
        assertThat(engine.evaluate(p, a, asOf).status()).isEqualTo(Eligibility.Status.INELIGIBLE);
        ((ObjectNode) a.path("security")).remove("collateralReady");
        assertThat(engine.evaluate(p, a, asOf).status()).isEqualTo(Eligibility.Status.CONDITIONAL);
    }

    @Test
    void removedCountersDoNotBecomeMissingFormFieldsButSpecialConditionsNeedReview() {
        var p = TestData.product();
        ((ObjectNode) p.policy().path("eligibility"))
                .putArray("extra_conditions")
                .add("MARKETPLACE_6_MONTHS");
        var result = engine.evaluate(p, TestData.preliminary(), asOf);
        assertThat(result.status()).isEqualTo(Eligibility.Status.CONDITIONAL);
        assertThat(result.missingFields()).isEmpty();
        assertThat(result.reasons())
                .anyMatch(r -> r.code().equals("ADDITIONAL_CONDITION_REQUIRES_REVIEW"));
    }

    @Test
    void unknownUsageSkipsCheckButIncompatibleUsageExcludesProduct() {
        var answers = TestData.preliminary();
        ((ObjectNode) answers.path("request")).put("usageMode", "UNKNOWN");
        assertThat(engine.evaluate(TestData.product(), answers, asOf).status())
                .isEqualTo(Eligibility.Status.ELIGIBLE);
        ((ObjectNode) answers.path("request")).put("usageMode", "ACCOUNT_RESERVE");
        assertThat(engine.evaluate(TestData.product(), answers, asOf).reasons())
                .anyMatch(
                        r ->
                                r.code().equals("USAGE_MODE_NOT_SUPPORTED")
                                        && r.result() == Eligibility.Outcome.FAIL);
    }

    @Test
    void shortHistoryRequiresReviewAndExcludedSectorIsChecked() {
        var p = TestData.product();
        var a = TestData.preliminary();
        ((ObjectNode) a.path("financial")).put("periodFrom", "2026-04-01");
        assertThat(engine.evaluate(p, a, asOf).status()).isEqualTo(Eligibility.Status.CONDITIONAL);
        ((ObjectNode) a.path("business")).put("sector", "GAMBLING");
        assertThat(engine.evaluate(p, a, asOf).status()).isEqualTo(Eligibility.Status.INELIGIBLE);
    }
}
