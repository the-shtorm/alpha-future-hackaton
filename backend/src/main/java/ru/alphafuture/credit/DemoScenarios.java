package ru.alphafuture.credit;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.charset.StandardCharsets;
import java.time.*;
import java.util.*;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.web.bind.annotation.*;

/** Восемь синтетических бизнес-сценариев для UI/Postman; не набор для обучения. */
@RestController
@Profile("demo")
class DemoScenarios {
    record Scenario(
            String code,
            String name,
            UUID partyId,
            JsonNode preliminaryAnswers,
            JsonNode applicationAdditionalAnswers,
            JsonNode financialEvidence,
            String expected) {}

    private final JdbcClient db;
    private final Json json;
    private final Access access;

    DemoScenarios(JdbcClient db, Json json, Access access) {
        this.db = db;
        this.json = json;
        this.access = access;
    }

    @GetMapping("/demo/scenarios")
    Map<String, Object> list() {
        var items = new ArrayList<Scenario>();
        for (var scenario : cases())
            if (access.bank()
                    || db.sql(
                                    "SELECT EXISTS(SELECT 1 FROM credit.party_membership WHERE party_id=:party AND user_id=:user AND revoked_at IS NULL)")
                            .param("party", scenario.partyId())
                            .param("user", access.user())
                            .query(Boolean.class)
                            .single()) items.add(scenario);
        return Map.of(
                "isSimulated",
                true,
                "purpose",
                "UI_AND_BACKEND_TESTING_NOT_TRAINING",
                "items",
                items);
    }

    void seed(UUID user) {
        int index = 1;
        for (var scenario : cases()) {
            String digits = "99000010" + index;
            int[] weights = {2, 4, 10, 3, 5, 9, 4, 6, 8};
            int sum = 0;
            for (int i = 0; i < 9; i++) sum += (digits.charAt(i) - '0') * weights[i];
            String taxId = digits + (sum % 11 % 10);
            db.sql(
                            "INSERT INTO credit.party(id,party_kind,name,tax_id,registered_on) VALUES (:id,'LLC',:name,:tax,'2020-01-01') ON CONFLICT DO NOTHING")
                    .param("id", scenario.partyId())
                    .param("name", "DEMO: " + scenario.name())
                    .param("tax", taxId)
                    .update();
            db.sql(
                            "INSERT INTO credit.party_membership(party_id,user_id,access_role) VALUES (:party,:user,'OWNER') ON CONFLICT DO NOTHING")
                    .param("party", scenario.partyId())
                    .param("user", user)
                    .update();
            db.sql(
                            "INSERT INTO credit.business_profile(party_id,profile_data,field_sources) VALUES (:party,CAST(:data AS jsonb),CAST(:source AS jsonb)) ON CONFLICT DO NOTHING")
                    .param("party", scenario.partyId())
                    .param("data", json.write(scenario))
                    .param(
                            "source",
                            json.write(Map.of("isSimulated", true, "source", "DEMO_SCENARIO_V1")))
                    .update();
            index++;
        }
    }

    List<Scenario> cases() {
        LocalDate end = LocalDate.now(ZoneOffset.UTC).withDayOfMonth(1).minusDays(1),
                start = end.plusDays(1).minusMonths(12);
        var base =
                json.read(
                        """
            {"request":{"amount":"1000000.00","termMonths":12,"purpose":"WORKING_CAPITAL","usageMode":"ONE_TIME"},
            "registration":{"borrowerKind":"LLC"},
            "business":{"actualStartedOn":"2020-01-01","sector":"TRADE","taxRegime":"USN","mspRegistry":true},
            "financial":{"revenue":"24000000.00"},"security":{"collateralReady":"NO","guarantorReady":"YES"}}
            """);
        ((ObjectNode) base.path("financial"))
                .put("periodFrom", start.toString())
                .put("periodTo", end.toString());
        var additional =
                json.read(
                        "{\"financial\":{\"monthlyDebtPayment\":\"0.00\",\"overdue\":0},\"security\":{\"collateralValue\":\"0.00\"},\"project\":{\"ownContributionPct\":\"0.00\"}}");
        var result = new ArrayList<Scenario>();
        result.add(
                scenario(
                        "STABLE",
                        "Устойчивый бизнес",
                        base,
                        additional,
                        json.mapper.createObjectNode(),
                        "DEMO_APPROVED_AFTER_CONTEXT_AND_DOCUMENT_CHECKS"));
        result.add(
                scenario(
                        "SEASONAL",
                        "Сезонные поступления",
                        base,
                        additional,
                        evidence(
                                start,
                                end,
                                new String[] {
                                    "500000.00",
                                    "500000.00",
                                    "500000.00",
                                    "1000000.00",
                                    "1000000.00",
                                    "1000000.00",
                                    "2000000.00",
                                    "3000000.00",
                                    "3000000.00",
                                    "4000000.00",
                                    "4000000.00",
                                    "3500000.00"
                                }),
                        "VERIFY_OPERATIONS_AND_SEASONALITY"));
        var debt = additional.deepCopy();
        ((ObjectNode) debt.path("financial")).put("monthlyDebtPayment", "950000.00");
        result.add(
                scenario(
                        "HIGH_DEBT",
                        "Высокая долговая нагрузка",
                        base,
                        debt,
                        json.mapper.createObjectNode(),
                        "DECLINED_NO_NEW_LOAN_BUDGET"));
        var missing = base.deepCopy();
        ((ObjectNode) missing.path("business")).remove("taxRegime");
        ((ObjectNode) missing.path("financial")).remove("revenue");
        result.add(
                scenario(
                        "MISSING_DATA",
                        "Недостаток данных",
                        missing,
                        additional,
                        json.mapper.createObjectNode(),
                        "CONDITIONAL_THEN_REQUEST_INFO"));
        result.add(
                scenario(
                        "REVENUE_MISMATCH",
                        "Расхождение выручки и операций",
                        base,
                        additional,
                        evidence(
                                start,
                                end,
                                Collections.nCopies(12, "1000000.00").toArray(String[]::new)),
                        "UNDER_REVIEW_AFTER_EVIDENCE_VERIFICATION"));
        var high = base.deepCopy();
        ((ObjectNode) high.path("financial")).put("revenue", "6000000.00");
        ((ObjectNode) high.path("request")).put("amount", "2800000.00");
        var highDebt = additional.deepCopy();
        ((ObjectNode) highDebt.path("financial")).put("monthlyDebtPayment", "130000.00");
        result.add(
                scenario(
                        "OVER_REQUESTED",
                        "Завышенная сумма",
                        high,
                        highDebt,
                        json.mapper.createObjectNode(),
                        "DEMO_COUNTEROFFER_WITH_VALID_MACRO_CONTEXT"));
        var secured = base.deepCopy();
        ((ObjectNode) secured.path("request"))
                .put("purpose", "EQUIPMENT")
                .put("amount", "3000000.00");
        ((ObjectNode) secured.path("security")).put("collateralReady", "YES");
        var security = additional.deepCopy();
        ((ObjectNode) security.path("security")).put("collateralValue", "4000000.00");
        ((ObjectNode) security.path("project")).put("ownContributionPct", "20.00");
        result.add(
                scenario(
                        "COLLATERAL",
                        "Обязательное обеспечение",
                        secured,
                        security,
                        json.mapper.createObjectNode(),
                        "COLLATERAL_AND_DOCUMENT_CHECKS"));
        var none = base.deepCopy();
        ((ObjectNode) none.path("request")).put("amount", "99999999999999.00");
        result.add(
                scenario(
                        "NO_PRODUCTS",
                        "Нет подходящих предложений",
                        none,
                        additional,
                        json.mapper.createObjectNode(),
                        "ALL_PRODUCTS_INELIGIBLE"));
        return result;
    }

    private Scenario scenario(
            String code,
            String name,
            JsonNode preliminary,
            JsonNode additional,
            JsonNode evidence,
            String expected) {
        return new Scenario(
                code,
                name,
                UUID.nameUUIDFromBytes(
                        ("backend-demo-2.1-" + code).getBytes(StandardCharsets.UTF_8)),
                preliminary.deepCopy(),
                additional.deepCopy(),
                evidence,
                expected);
    }

    private JsonNode evidence(LocalDate from, LocalDate to, String[] amounts) {
        var node = json.mapper.createObjectNode();
        node.put("periodFrom", from.toString()).put("periodTo", to.toString());
        var rows = node.putArray("operations");
        for (int i = 0; i < amounts.length; i++)
            rows.addObject()
                    .put("externalId", "demo-operation-" + i)
                    .put("date", from.plusMonths(i).toString())
                    .put("amount", amounts[i])
                    .put("direction", "CREDIT")
                    .put("category", "REVENUE");
        return node;
    }
}
