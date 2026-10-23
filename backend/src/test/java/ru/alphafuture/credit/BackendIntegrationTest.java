package ru.alphafuture.credit;

import static org.assertj.core.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.file.*;
import java.sql.*;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.*;
import org.springframework.test.web.servlet.*;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.*;

/** Backend 2.1 против реального PostgreSQL: формы, права, бюджет и акцепт альтернативы. */
@Testcontainers
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("demo")
class BackendIntegrationTest {
    @Container
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:17-bookworm")
                    .withInitScript("db/api_test_roles.sql");

    static final String PASSWORD = "local-integration-password";
    static final Path STORAGE;

    static {
        try {
            STORAGE = Files.createTempDirectory("backend-policy21-documents-");
        } catch (Exception ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry r) {
        r.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        r.add("spring.datasource.username", () -> "credit_app");
        r.add("spring.datasource.password", () -> "runtime-test-password");
        r.add("spring.flyway.url", POSTGRES::getJdbcUrl);
        r.add("spring.flyway.user", POSTGRES::getUsername);
        r.add("spring.flyway.password", POSTGRES::getPassword);
        r.add("cabinet.demo-password", () -> PASSWORD);
        r.add("cabinet.demo-bank-password", () -> PASSWORD);
        r.add("cabinet.documents-path", STORAGE::toString);
        r.add("cabinet.demo-assessment-enabled", () -> true);
    }

    @Autowired MockMvc http;
    @Autowired ObjectMapper mapper;
    @Autowired JdbcClient db;
    static String owner, bank;
    UUID party, product;

    @BeforeEach
    void setup() throws Exception {
        if (owner == null) owner = login("demo-owner");
        if (bank == null) bank = login("demo-bank");
        for (var p : get("/me", owner).path("parties"))
            if (p.path("tax_id").asText().equals("7707083893"))
                party = UUID.fromString(p.path("id").asText());
        product =
                db.sql(
                                "SELECT v.id FROM credit.credit_product_version v JOIN credit.credit_product p ON p.id=v.product_id WHERE p.code='P01'")
                        .query(UUID.class)
                        .single();
        macro("10.00000");
    }

    String login(String name) throws Exception {
        return post("/auth/login", null, Map.of("login", name, "password", PASSWORD))
                .path("accessToken")
                .asText();
    }

    JsonNode request(
            org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder request,
            int status)
            throws Exception {
        return mapper.readTree(
                http.perform(request)
                        .andExpect(status().is(status))
                        .andReturn()
                        .getResponse()
                        .getContentAsString());
    }

    JsonNode get(String path, String token) throws Exception {
        var req = org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get(path);
        if (token != null) req.header("Authorization", "Bearer " + token);
        return request(req, 200);
    }

    JsonNode post(String path, String token, Object body) throws Exception {
        return send(
                org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post(path),
                token,
                body,
                200);
    }

    JsonNode send(
            org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder req,
            String token,
            Object body,
            int expected)
            throws Exception {
        if (token != null) req.header("Authorization", "Bearer " + token);
        return request(
                req.contentType(MediaType.APPLICATION_JSON)
                        .content(mapper.writeValueAsString(body)),
                expected);
    }

    JsonNode macro(String rate) throws Exception {
        return post(
                "/bank/macroeconomic-contexts",
                bank,
                Map.of(
                        "keyRatePct",
                        rate,
                        "validFrom",
                        Instant.now().minusSeconds(1).toString(),
                        "expiresAt",
                        Instant.now().plusSeconds(86400).toString(),
                        "sourceCode",
                        "DEMO_FIXTURE_NOT_CBR"));
    }

    JsonNode profile(ObjectNode preliminary) throws Exception {
        return post("/selection-profiles", owner, Map.of("partyId", party, "answers", preliminary));
    }

    JsonNode select(JsonNode profile) throws Exception {
        var run =
                post(
                        "/selection-profiles/" + profile.path("id").asText() + "/eligibility",
                        owner,
                        Map.of());
        return send(
                put("/selection-profiles/" + profile.path("id").asText() + "/selected-product"),
                owner,
                Map.of(
                        "expectedVersion",
                        profile.path("rowVersion").asLong(),
                        "runId",
                        run.path("runId").asText(),
                        "productVersionId",
                        product),
                200);
    }

    JsonNode draft(ObjectNode preliminary, ObjectNode additions) throws Exception {
        var selected = select(profile(preliminary));
        return post(
                "/applications",
                owner,
                Map.of(
                        "profileId",
                        selected.path("id").asText(),
                        "expectedProfileVersion",
                        selected.path("rowVersion").asLong(),
                        "answers",
                        additions));
    }

    JsonNode ready(ObjectNode preliminary, ObjectNode additions) throws Exception {
        var app = draft(preliminary, additions);
        String id = app.path("id").asText();
        for (var requirement : get("/applications/" + id + "/requirements", owner)) {
            var version = upload(id, requirement.path("type_code").asText());
            post(
                    "/bank/applications/"
                            + id
                            + "/documents/"
                            + version.path("versionId").asText()
                            + "/review",
                    bank,
                    Map.of("result", "PASS", "reason", "DEMO manual verification"));
        }
        return get("/applications/" + id, owner);
    }

    JsonNode upload(String app, String type) throws Exception {
        var file =
                new MockMultipartFile(
                        "file", "statement.pdf", "application/pdf", "%PDF-1.7\nfixture".getBytes());
        return request(
                multipart("/applications/" + app + "/documents")
                        .file(file)
                        .param("typeCode", type)
                        .header("Authorization", "Bearer " + owner),
                200);
    }

    JsonNode submit(JsonNode app, String key) throws Exception {
        return send(
                org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post(
                                "/applications/" + app.path("id").asText() + "/submit")
                        .header("Idempotency-Key", key),
                owner,
                Map.of("expectedVersion", app.path("rowVersion").asLong(), "confirmed", true),
                200);
    }

    JsonNode process(JsonNode app) throws Exception {
        return post("/bank/applications/" + app.path("id").asText() + "/process", bank, Map.of());
    }

    @Test
    void onlyElevenFieldsTransferAndSelectionNeverReceivesFinalData() throws Exception {
        var p = select(profile(TestData.preliminary()));
        var app =
                post(
                        "/applications",
                        owner,
                        Map.of(
                                "profileId",
                                p.path("id").asText(),
                                "expectedProfileVersion",
                                p.path("rowVersion").asLong(),
                                "answers",
                                Map.of()));
        assertThat(app.path("answers").path("registration").has("country")).isFalse();
        assertThat(app.path("answers").path("business").has("sector")).isFalse();
        assertThat(app.path("answers").path("financial").has("overdue")).isFalse();
        assertThat(
                        app.path("preliminaryContext")
                                .path("answers")
                                .path("business")
                                .path("sector")
                                .asText())
                .isEqualTo("TRADE");
        var snapshot =
                db.sql("SELECT profile_snapshot FROM credit.recommendation_run WHERE id=:id")
                        .param("id", UUID.fromString(p.path("selectedRunId").asText()))
                        .query(String.class)
                        .single();
        assertThat(mapper.readTree(snapshot).path("answers").path("financial").has("overdue"))
                .isFalse();
        assertThat(
                        app.path("fieldSources")
                                .path("financial.revenue")
                                .path("verification_status")
                                .asText())
                .isEqualTo("DECLARED");
        send(
                org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post(
                        "/selection-profiles"),
                owner,
                Map.of("partyId", party, "answers", Map.of("financial", Map.of("overdue", 0.1))),
                400);
        send(
                org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post(
                        "/applications"),
                owner,
                Map.of(
                        "profileId",
                        p.path("id").asText(),
                        "expectedProfileVersion",
                        p.path("rowVersion").asLong(),
                        "answers",
                        Map.of("business", Map.of("sector", "TRADE"))),
                400);
    }

    @Test
    void changedProfileInvalidatesSelectionAndOldRunRemainsImmutable() throws Exception {
        var p = profile(TestData.preliminary());
        String id = p.path("id").asText();
        var run = post("/selection-profiles/" + id + "/eligibility", owner, Map.of());
        var before =
                get(
                        "/selection-profiles/"
                                + id
                                + "/recommendations/"
                                + run.path("runId").asText(),
                        owner);
        send(
                patch("/selection-profiles/" + id),
                owner,
                Map.of(
                        "expectedVersion",
                        0,
                        "answers",
                        Map.of("request", Map.of("amount", "1100000.00"))),
                200);
        send(
                put("/selection-profiles/" + id + "/selected-product"),
                owner,
                Map.of(
                        "expectedVersion",
                        1,
                        "runId",
                        run.path("runId").asText(),
                        "productVersionId",
                        product),
                409);
        var after =
                get(
                        "/selection-profiles/"
                                + id
                                + "/recommendations/"
                                + run.path("runId").asText(),
                        owner);
        assertThat(after.path("current").asBoolean()).isFalse();
        assertThat(after.path("items")).isEqualTo(before.path("items"));
    }

    @Test
    void preliminaryFormCanBePartialAndNoProductsIsNotCreditDecline() throws Exception {
        var p = profile((ObjectNode) mapper.readTree("{}"));
        var run =
                post(
                        "/selection-profiles/" + p.path("id").asText() + "/eligibility",
                        owner,
                        Map.of());
        assertThat(run.path("items"))
                .allSatisfy(
                        item -> assertThat(item.path("status").asText()).isEqualTo("CONDITIONAL"));
        var a = TestData.preliminary();
        ((ObjectNode) a.path("request")).put("amount", "99999999999999.00");
        p = profile(a);
        run =
                post(
                        "/selection-profiles/" + p.path("id").asText() + "/eligibility",
                        owner,
                        Map.of());
        assertThat(run.path("items"))
                .allSatisfy(
                        item -> assertThat(item.path("status").asText()).isEqualTo("INELIGIBLE"));
        send(
                put("/selection-profiles/" + p.path("id").asText() + "/selected-product"),
                owner,
                Map.of(
                        "expectedVersion",
                        0,
                        "runId",
                        run.path("runId").asText(),
                        "productVersionId",
                        product),
                422);
    }

    @Test
    void missingInformationReturnsRequestInfoAndResubmissionDoesNotRewriteHistory()
            throws Exception {
        var add = TestData.additions();
        ((ObjectNode) add.path("financial")).remove("overdue");
        var app = ready(TestData.preliminary(), add);
        String id = app.path("id").asText(), key = UUID.randomUUID().toString();
        var first = submit(app, key);
        var old =
                get(
                        "/applications/" + id + "/revisions/" + first.path("revisionId").asText(),
                        owner);
        var processed = process(app);
        assertThat(processed.path("decision").path("kind").asText()).isEqualTo("REQUEST_INFO");
        assertThat(processed.has("offer")).isFalse();
        assertThat(submit(app, key).path("revisionId")).isEqualTo(first.path("revisionId"));
        var edited =
                send(
                        patch("/applications/" + id),
                        owner,
                        Map.of(
                                "expectedVersion",
                                processed.path("application").path("rowVersion").asLong(),
                                "answers",
                                Map.of("financial", Map.of("overdue", 0))),
                        200);
        var next = submit(edited, UUID.randomUUID().toString());
        assertThat(next.path("revisionId")).isNotEqualTo(first.path("revisionId"));
        assertThat(
                        get(
                                "/applications/"
                                        + id
                                        + "/revisions/"
                                        + first.path("revisionId").asText(),
                                owner))
                .isEqualTo(old);
    }

    @Test
    void automaticDemoApprovalIsExplicitAndCompletesOneDemoDisbursement() throws Exception {
        var app = ready(TestData.preliminary(), TestData.additions());
        String id = app.path("id").asText();
        submit(app, UUID.randomUUID().toString());
        var journey = process(app);
        assertThat(journey.path("application").path("status").asText()).isEqualTo("APPROVED");
        assertThat(
                        journey.path("decision")
                                .path("conditions")
                                .path("assessment")
                                .path("mode")
                                .asText())
                .isEqualTo("DEMO");
        post(
                "/applications/" + id + "/offers/accept",
                owner,
                Map.of("offerId", journey.path("offer").path("id").asText(), "confirmed", true));
        post("/applications/" + id + "/contract/sign", owner, Map.of("confirmed", true));
        journey = post("/bank/applications/" + id + "/disburse", bank, Map.of("confirmed", true));
        assertThat(journey.path("application").path("status").asText()).isEqualTo("DISBURSED");
        assertThat(journey.path("disbursements")).hasSize(1);
        send(
                org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post(
                        "/bank/applications/" + id + "/disburse"),
                bank,
                Map.of("confirmed", true),
                409);
    }

    @Test
    void counterofferCreatesOfferOnlyAfterExactAcceptanceAndKeepsOriginalRequest()
            throws Exception {
        var pre = TestData.preliminary();
        ((ObjectNode) pre.path("request")).put("amount", "2800000.00");
        ((ObjectNode) pre.path("financial")).put("revenue", "6000000.00");
        var add = TestData.additions();
        ((ObjectNode) add.path("financial")).put("monthlyDebtPayment", "130000.00");
        var app = ready(pre, add);
        String id = app.path("id").asText();
        var revision = submit(app, UUID.randomUUID().toString());
        var journey = process(app);
        assertThat(journey.path("decision").path("kind").asText()).isEqualTo("COUNTEROFFERED");
        assertThat(journey.has("offer")).isFalse();
        var proposal = journey.path("counteroffer");
        String saved = proposal.path("alternative_terms").toString();
        send(
                org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post(
                        "/applications/" + id + "/counteroffers/accept"),
                owner,
                Map.of(
                        "proposalId",
                        proposal.path("id").asText(),
                        "termsSha256",
                        "0".repeat(64),
                        "confirmed",
                        true),
                409);
        macro("12.00000");
        var body =
                Map.of(
                        "proposalId",
                        proposal.path("id").asText(),
                        "termsSha256",
                        proposal.path("termsSha256").asText(),
                        "confirmed",
                        true);
        var accepted = post("/applications/" + id + "/counteroffers/accept", owner, body);
        assertThat(accepted.path("application").path("status").asText())
                .isEqualTo("OFFER_ACCEPTED");
        assertThat(accepted.path("offer").path("terms").path("amount"))
                .isEqualTo(proposal.path("alternative_terms").path("amount"));
        assertThat(accepted.path("decision").path("conditions").path("key_rate_pct").asText())
                .isEqualTo("10.00000");
        assertThat(accepted.path("counteroffer").path("alternative_terms").toString())
                .isEqualTo(saved);
        var replay = post("/applications/" + id + "/counteroffers/accept", owner, body);
        assertThat(replay.path("offer").path("id")).isEqualTo(accepted.path("offer").path("id"));
        assertThat(
                        get(
                                        "/applications/"
                                                + id
                                                + "/revisions/"
                                                + revision.path("revisionId").asText(),
                                        owner)
                                .path("snapshot")
                                .path("answers")
                                .path("request")
                                .path("amount")
                                .asText())
                .isEqualTo("2800000.00");
        post("/applications/" + id + "/contract/sign", owner, Map.of("confirmed", true));
        var disbursed =
                post("/bank/applications/" + id + "/disburse", bank, Map.of("confirmed", true));
        assertThat(disbursed.path("disbursements").get(0).path("amount").asText())
                .isEqualTo(proposal.path("alternative_terms").path("amount").asText());
    }

    @Test
    void hardOverdueAndNoBudgetCannotBeOverriddenByBank() throws Exception {
        var add = TestData.additions();
        ((ObjectNode) add.path("financial"))
                .put("overdue", new java.math.BigDecimal("0.200000000001"));
        var app = ready(TestData.preliminary(), add);
        submit(app, UUID.randomUUID().toString());
        String id = app.path("id").asText();
        send(
                org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post(
                        "/bank/applications/" + id + "/decisions"),
                bank,
                Map.of("kind", "COUNTEROFFERED", "reason", "Нельзя обходить запрет"),
                422);
        var result = process(app);
        assertThat(result.path("decision").path("kind").asText()).isEqualTo("DECLINED");
        assertThat(result.has("counteroffer")).isFalse();
        add = TestData.additions();
        ((ObjectNode) add.path("financial")).put("monthlyDebtPayment", "800000.00");
        app = ready(TestData.preliminary(), add);
        submit(app, UUID.randomUUID().toString());
        assertThat(process(app).path("decision").path("kind").asText()).isEqualTo("DECLINED");
    }

    @Test
    void unknownDocumentsForceRequestInfoAndClientCannotVerifyThem() throws Exception {
        var app = draft(TestData.preliminary(), TestData.additions());
        String id = app.path("id").asText();
        var version = upload(id, "GUARANTEE_CONTRACT");
        app = get("/applications/" + id, owner);
        submit(app, UUID.randomUUID().toString());
        var r = process(app);
        assertThat(r.path("decision").path("kind").asText()).isEqualTo("REQUEST_INFO");
        assertThat(r.path("decision").path("conditions").path("missingFields").toString())
                .contains("documents.");
        send(
                org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post(
                        "/bank/applications/"
                                + id
                                + "/documents/"
                                + version.path("versionId").asText()
                                + "/review"),
                owner,
                Map.of("result", "PASS", "reason", "Нельзя"),
                403);
        http.perform(
                        org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get(
                                        "/applications/"
                                                + id
                                                + "/documents/"
                                                + version.path("versionId").asText())
                                .header("Authorization", "Bearer " + owner))
                .andExpect(status().isOk())
                .andExpect(content().bytes("%PDF-1.7\nfixture".getBytes()));
    }

    @Test
    void verifiedRevenueMismatchEntersReviewAndKeepsOperationsOutsideAnswers() throws Exception {
        var app = ready(TestData.preliminary(), TestData.additions());
        String id = app.path("id").asText();
        var evidence =
                post(
                        "/applications/" + id + "/financial-evidence",
                        owner,
                        Map.of(
                                "periodFrom",
                                "2025-10-01",
                                "periodTo",
                                "2026-09-30",
                                "operations",
                                List.of(
                                        Map.of(
                                                "externalId",
                                                "one",
                                                "date",
                                                "2026-01-01",
                                                "amount",
                                                "12000000.00",
                                                "direction",
                                                "CREDIT",
                                                "category",
                                                "REVENUE"))));
        post(
                "/bank/applications/"
                        + id
                        + "/financial-evidence/"
                        + evidence.path("id").asText()
                        + "/review",
                bank,
                Map.of("result", "PASS", "reason", "Проверены операции"));
        app = get("/applications/" + id, owner);
        submit(app, UUID.randomUUID().toString());
        var r = process(app);
        assertThat(r.path("application").path("status").asText()).isEqualTo("UNDER_REVIEW");
        assertThat(
                        get("/applications/" + id + "/financial-evidence", bank)
                                .get(0)
                                .path("operations"))
                .hasSize(1);
        assertThat(r.path("checks").get(0).path("result").asText()).isEqualTo("REVIEW");
        assertThat(r.path("checks").get(0).path("evidence").path("reasonCode").asText())
                .isEqualTo("MANUAL_REVIEW_REQUIRED");
        assertThat(r.has("decision")).isFalse();
        assertThat(r.path("application").path("answers").has("operations")).isFalse();
        r =
                post(
                        "/bank/applications/" + id + "/decisions",
                        bank,
                        Map.of(
                                "kind",
                                "REQUEST_INFO",
                                "reason",
                                "Уточните заявленную выручку",
                                "missingFields",
                                List.of("financial.revenue")));
        assertThat(r.path("application").path("status").asText()).isEqualTo("NEEDS_INFO");
    }

    @Test
    void operationsExcludeInternalTransfersAndLoansAndRejectDuplicates() throws Exception {
        var app = draft(TestData.preliminary(), TestData.additions());
        String id = app.path("id").asText();
        var revenue =
                Map.of(
                        "externalId",
                        "revenue",
                        "date",
                        "2026-01-01",
                        "amount",
                        "100.00",
                        "direction",
                        "CREDIT",
                        "category",
                        "REVENUE");
        var payload =
                Map.of(
                        "periodFrom",
                        "2025-10-01",
                        "periodTo",
                        "2026-09-30",
                        "operations",
                        List.of(
                                revenue,
                                Map.of(
                                        "externalId",
                                        "loan",
                                        "date",
                                        "2026-01-01",
                                        "amount",
                                        "500.00",
                                        "direction",
                                        "CREDIT",
                                        "category",
                                        "LOAN"),
                                Map.of(
                                        "externalId",
                                        "internal",
                                        "date",
                                        "2026-01-01",
                                        "amount",
                                        "500.00",
                                        "direction",
                                        "CREDIT",
                                        "category",
                                        "INTERNAL_TRANSFER")));
        assertThat(
                        post("/applications/" + id + "/financial-evidence", owner, payload)
                                .path("revenue")
                                .asText())
                .isEqualTo("100.00");
        send(
                org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post(
                        "/applications/" + id + "/financial-evidence"),
                owner,
                Map.of(
                        "periodFrom",
                        "2025-10-01",
                        "periodTo",
                        "2026-09-30",
                        "operations",
                        List.of(revenue, revenue)),
                400);
    }

    @Test
    void refreshingPreliminaryContextDoesNotRewriteSubmittedRevisionOrFinalAnswers()
            throws Exception {
        var pre = TestData.preliminary();
        ((ObjectNode) pre.path("registration")).remove("country");
        var app = ready(pre, TestData.additions());
        String id = app.path("id").asText();
        var first = submit(app, UUID.randomUUID().toString());
        var result = process(app);
        assertThat(result.path("decision").path("conditions").path("missingFields").toString())
                .contains("preliminary.registration.country");
        var p = get("/selection-profiles/" + app.path("profileId").asText(), owner);
        p =
                send(
                        patch("/selection-profiles/" + p.path("id").asText()),
                        owner,
                        Map.of(
                                "expectedVersion",
                                p.path("rowVersion").asLong(),
                                "answers",
                                Map.of("registration", Map.of("country", "RU"))),
                        200);
        p = select(p);
        var refreshed =
                post(
                        "/applications/" + id + "/refresh-preliminary",
                        owner,
                        Map.of(
                                "expectedVersion",
                                result.path("application").path("rowVersion").asLong(),
                                "expectedProfileVersion",
                                p.path("rowVersion").asLong()));
        assertThat(refreshed.path("answers")).isEqualTo(app.path("answers"));
        submit(refreshed, UUID.randomUUID().toString());
        assertThat(process(refreshed).path("application").path("status").asText())
                .isEqualTo("APPROVED");
        assertThat(
                        get(
                                        "/applications/"
                                                + id
                                                + "/revisions/"
                                                + first.path("revisionId").asText(),
                                        owner)
                                .path("snapshot")
                                .path("preliminaryContext")
                                .path("answers")
                                .path("registration")
                                .has("country"))
                .isFalse();
    }

    @Test
    void rolesIsolationLockingRevocationAndSealedContextAreEnforced() throws Exception {
        var app = ready(TestData.preliminary(), TestData.additions());
        String id = app.path("id").asText();
        String viewer = account("VIEWER", party, false),
                editor = account("EDITOR", party, false),
                stranger = account(null, null, false),
                otherBank = account(null, null, true);
        get("/applications/" + id, viewer);
        send(
                patch("/applications/" + id),
                viewer,
                Map.of("expectedVersion", app.path("rowVersion").asLong(), "answers", Map.of()),
                403);
        send(
                patch("/applications/" + id),
                editor,
                Map.of("expectedVersion", 999, "answers", Map.of()),
                409);
        http.perform(
                        org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get(
                                        "/applications/" + id)
                                .header("Authorization", "Bearer " + stranger))
                .andExpect(status().isNotFound());
        submit(app, UUID.randomUUID().toString());
        post("/bank/applications/" + id + "/assign", bank, Map.of());
        send(
                org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post(
                        "/bank/applications/" + id + "/process"),
                otherBank,
                Map.of(),
                409);
        assertThatThrownBy(
                        () ->
                                db.sql(
                                                "UPDATE credit.loan_application SET source_preliminary_snapshot='{}'::jsonb WHERE id=:id")
                                        .param("id", UUID.fromString(id))
                                        .update())
                .isInstanceOf(org.springframework.dao.DataAccessException.class);
        post("/auth/logout", viewer, Map.of());
        http.perform(
                        org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get(
                                        "/applications/" + id)
                                .header("Authorization", "Bearer " + viewer))
                .andExpect(status().isUnauthorized());
    }

    String account(String role, UUID company, boolean isBank) throws Exception {
        UUID user = UUID.randomUUID();
        String name = "fixture-" + user;
        String hash =
                org.springframework.security.crypto.factory.PasswordEncoderFactories
                        .createDelegatingPasswordEncoder()
                        .encode(PASSWORD);
        try (var c =
                DriverManager.getConnection(
                        POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword())) {
            try (var q =
                    c.prepareStatement(
                            "INSERT INTO credit.app_user(id,login,password_hash,display_name) VALUES (?,?,?,'Fixture')")) {
                q.setObject(1, user);
                q.setString(2, name);
                q.setString(3, hash);
                q.executeUpdate();
            }
            if (company != null)
                try (var q =
                        c.prepareStatement(
                                "INSERT INTO credit.party_membership(party_id,user_id,access_role) VALUES (?,?,?)")) {
                    q.setObject(1, company);
                    q.setObject(2, user);
                    q.setString(3, role);
                    q.executeUpdate();
                }
            if (isBank)
                try (var q =
                        c.prepareStatement(
                                "INSERT INTO credit.user_role(user_id,role_code) VALUES (?,'BANK_APPROVER')")) {
                    q.setObject(1, user);
                    q.executeUpdate();
                }
        }
        return login(name);
    }

    @Test
    void publicSchemasDemoCasesAndOriginalSqlInvariantsRemainValid() throws Exception {
        assertThat(get("/forms/preliminary", owner).path("fields")).hasSize(19);
        assertThat(get("/forms/application", owner).path("fields")).hasSize(15);
        assertThat(get("/demo/scenarios", owner).path("items")).hasSize(8);
        assertThat(get("/products", null).path("totalElements").asInt()).isEqualTo(15);
        assertThat(
                        get("/v3/api-docs", owner)
                                .path("paths")
                                .has("/applications/{id}/counteroffers/accept"))
                .isTrue();
        send(
                org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post(
                        "/bank/macroeconomic-contexts"),
                owner,
                Map.of(
                        "keyRatePct",
                        "10",
                        "validFrom",
                        Instant.now().minusSeconds(60).toString(),
                        "expiresAt",
                        Instant.now().plusSeconds(60).toString(),
                        "sourceCode",
                        "forbidden"),
                403);
        assertThatThrownBy(
                        () ->
                                db.sql("UPDATE credit.macroeconomic_context SET key_rate_pct=99")
                                        .update())
                .isInstanceOf(org.springframework.dao.DataAccessException.class);
        try (var c =
                        DriverManager.getConnection(
                                POSTGRES.getJdbcUrl(),
                                POSTGRES.getUsername(),
                                POSTGRES.getPassword());
                var q = c.createStatement()) {
            q.execute(
                    new String(
                            getClass()
                                    .getResourceAsStream("/db/database_invariants.sql")
                                    .readAllBytes(),
                            java.nio.charset.StandardCharsets.UTF_8));
        }
    }
}
