package ru.alphafuture.credit;

import static org.assertj.core.api.Assertions.*;

import com.fasterxml.jackson.databind.node.ObjectNode;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;

/** Границы новой формы: устаревшие поля, типы, словари и отсутствие будущих данных. */
class FormContractTest {
    final FormPolicy form = new FormPolicy();

    @Test
    void removedFieldsAreRejectedInsteadOfSilentlyEnteringSnapshots() {
        for (String path :
                List.of(
                        "registration.registeredOn",
                        "registration.country",
                        "business.region",
                        "business.ipAgeYears",
                        "business.marketplaceMonths",
                        "business.bankAccountMonths")) {
            var a = TestData.preliminary();
            var parts = path.split("\\.");
            ((ObjectNode) a.path(parts[0])).put(parts[1], "2020-01-01");
            assertThatThrownBy(() -> form.validatePreliminary(a))
                    .isInstanceOfSatisfying(
                            ApiFailure.class,
                            ex -> {
                                assertThat(ex.status).isEqualTo(400);
                                assertThat(ex.code).isEqualTo("INVALID_INPUT");
                                assertThat(ex.fields).contains(path);
                            });
        }
    }

    @Test
    void allSevenSectorsAreSharedButOldCodesAndTaxRegimesAreNotAccepted() {
        for (String code :
                List.of(
                        "TRADE",
                        "MANUFACTURING",
                        "SERVICES",
                        "IT",
                        "CONSTRUCTION",
                        "AGRICULTURE",
                        "LOGISTICS")) {
            var a = TestData.application();
            ((ObjectNode) a.path("business")).put("sector", code);
            form.validate(a);
        }
        for (String code : List.of("TRANSPORT", "OTHER", "GAMBLING")) {
            var a = TestData.preliminary();
            ((ObjectNode) a.path("business")).put("sector", code);
            assertThatThrownBy(() -> form.validatePreliminary(a)).isInstanceOf(ApiFailure.class);
        }
        var a = TestData.application();
        ((ObjectNode) a.path("business")).put("taxRegime", "PSN");
        assertThatThrownBy(() -> form.validate(a)).isInstanceOf(ApiFailure.class);
        ((ObjectNode) a.path("registration")).put("borrowerKind", "IP");
        form.validate(a);
        ((ObjectNode) a.path("business")).put("taxRegime", "COMBINED");
        assertThatThrownBy(() -> form.validate(a)).isInstanceOf(ApiFailure.class);
    }

    @Test
    void termIsAnIntegerFromOneTo360AndMoneyRequiresTwoDecimalPlaces() {
        for (int value : List.of(0, 361)) {
            var a = TestData.preliminary();
            ((ObjectNode) a.path("request")).put("termMonths", value);
            assertThatThrownBy(() -> form.validatePreliminary(a)).isInstanceOf(ApiFailure.class);
        }
        var a = TestData.preliminary();
        ((ObjectNode) a.path("request")).put("termMonths", 360);
        form.validatePreliminary(a);
        ((ObjectNode) a.path("request")).put("termMonths", new BigDecimal("12.0"));
        assertThatThrownBy(() -> form.validatePreliminary(a)).isInstanceOf(ApiFailure.class);
        for (String money : List.of("100", "100.1", "100.001", "-1.00", "01.00")) {
            ((ObjectNode) a.path("request")).put("termMonths", 12).put("amount", money);
            assertThatThrownBy(() -> form.validatePreliminary(a)).isInstanceOf(ApiFailure.class);
        }
        ((ObjectNode) a.path("request")).put("amount", 100);
        assertThatThrownBy(() -> form.validatePreliminary(a)).isInstanceOf(ApiFailure.class);
    }

    @Test
    void finalUnknownsRequestInformationAndVoluntaryCollateralNeedsAnActualValue() {
        var policy =
                new DataPolicy(
                        form,
                        new Payments(),
                        new DemoAssessment(false),
                        new MacroContext(null, null));
        for (String path :
                List.of(
                        "business.sector",
                        "business.taxRegime",
                        "security.collateralReady",
                        "security.guarantorReady")) {
            var a = TestData.application();
            var parts = path.split("\\.");
            ((ObjectNode) a.path(parts[0])).put(parts[1], "UNKNOWN");
            var review =
                    policy.review(a, TestData.product(), Instant.parse("2026-10-24T10:00:00Z"));
            assertThat(review.kind()).isEqualTo(DataPolicy.Kind.REQUEST_INFO);
            assertThat(review.conditions().get("missingFields").toString()).contains(path);
        }
        var a = TestData.application();
        ((ObjectNode) a.path("security")).put("collateralReady", "YES");
        var review = policy.review(a, TestData.product(), Instant.parse("2026-10-24T10:00:00Z"));
        assertThat(review.kind()).isEqualTo(DataPolicy.Kind.REQUEST_INFO);
        assertThat(review.conditions().get("missingFields"))
                .isEqualTo(List.of("security.collateralValue"));
    }

    @Test
    void onlyUsageAndDescriptionStayOutsideFinalApplication() {
        var a = TestData.preliminary();
        ((ObjectNode) a.path("request")).put("description", "Закупка товаров");
        ((ObjectNode) a.path("business")).put("sector", "IT");
        var transferred = FormPolicy.project(a, FormPolicy.TRANSFER_FIELDS);
        assertThat(transferred.path("request").has("description")).isFalse();
        assertThat(transferred.path("request").has("usageMode")).isFalse();
        assertThat(transferred.path("business").path("sector").asText()).isEqualTo("IT");
        assertThat(transferred.path("security")).isEqualTo(a.path("security"));
        assertThat(transferred.path("business").path("mspRegistry").isBoolean()).isTrue();
        assertThat(transferred.path("business").path("mspRegistry").asBoolean()).isFalse();
    }
}
