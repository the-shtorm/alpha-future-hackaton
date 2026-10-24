package ru.alphafuture.credit;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.util.*;

/** Синтетические входные формы и продукт для проверок; не обучение. */
class TestData {
    static final ObjectMapper MAPPER =
            new ObjectMapper()
                    .findAndRegisterModules()
                    .enable(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS);
    static final Json JSON = new Json(MAPPER);

    static ObjectNode preliminary() {
        return (ObjectNode)
                JSON.read(
                        """
        {"request":{"purpose":"WORKING_CAPITAL","usageMode":"ONE_TIME","amount":"1000000.00","termMonths":12},
        "registration":{"borrowerKind":"LLC"},
        "business":{"actualStartedOn":"2020-01-01","sector":"TRADE","taxRegime":"USN","mspRegistry":false},
        "financial":{"revenue":"24000000.00","periodFrom":"2025-10-01","periodTo":"2026-09-30"},"security":{"collateralReady":"NO","guarantorReady":"YES"}}
        """);
    }

    static ObjectNode additions() {
        return (ObjectNode)
                JSON.read(
                        "{\"financial\":{\"monthlyDebtPayment\":\"0.00\",\"overdue\":0},\"security\":{\"collateralValue\":\"0.00\"},\"project\":{\"ownContributionPct\":\"0.00\"}}");
    }

    static ObjectNode application() {
        return JSON.merge(
                FormPolicy.project(preliminary(), FormPolicy.TRANSFER_FIELDS), additions());
    }

    static Catalog.Product product() {
        var policy =
                JSON.read(
                        """
            {"facility_kind":"TERM","repayment":"ANNUITY","pricing":{"rate_type":"FIXED","maintenance_fee_rub":0,"issue_fee_rub":0},
            "eligibility":{"min_business_age_months":6,"min_average_monthly_revenue_rub":500000,"revenue_window_months":12,"country":"RU","regions":"ALL_RU_FOR_DEMO","min_ip_age_years":18,"tax_regimes":["USN","OSNO"],"extra_conditions":[]},
            "common_policy":{"excluded_sectors":["GAMBLING"]},"collateral":{"required":false,"min_own_contribution_pct":0},
            "guarantor":{"LLC":"CONTROLLING_OWNER_PERSONAL_GUARANTEE_REQUIRED"},"counteroffer":{"allowed":true,"allowedChanges":["AMOUNT_DECREASE","RATE_INCREASE"],"maxAnnualRatePct":100}}
            """);
        return new Catalog.Product(
                UUID.randomUUID(),
                UUID.randomUUID(),
                "P01",
                "Demo",
                "RUB",
                "300000.00",
                "3000000.00",
                6,
                24,
                "28.00000",
                JSON.read("[\"LLC\",\"IP\"]"),
                JSON.read("[\"WORKING_CAPITAL\",\"DEVELOPMENT\"]"),
                policy,
                true);
    }
}
