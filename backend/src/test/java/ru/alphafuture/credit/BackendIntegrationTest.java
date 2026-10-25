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
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.*;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
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

    static final ScoringStub SCORING = new ScoringStub();

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
        r.add("cabinet.recsys.url", () -> "");
        r.add("cabinet.scoring.url", SCORING::url);
        r.add("cabinet.scoring.api-key", () -> "fixture-key");
    }

    @Autowired MockMvc http;
    @Autowired ObjectMapper mapper;
    @Autowired JdbcClient db;
    @MockitoSpyBean ScoringGateway scoringGateway;
    static String owner, bank;
    UUID party, product;

    @BeforeEach
    void setup() throws Exception {
        SCORING.reset();
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
    void onlyThirteenFieldsTransferAndSelectionNeverReceivesFinalData() throws Exception {
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
        assertThat(app.path("answers").path("business").path("sector").asText()).isEqualTo("TRADE");
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
                        Map.of("request", Map.of("usageMode", "ONE_TIME"))),
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
        send(
                org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post(
                        "/selection-profiles/" + p.path("id").asText() + "/eligibility"),
                owner,
                Map.of(),
                400);
        var partial = TestData.preliminary();
        partial.remove("financial");
        p = profile(partial);
        var run =
                post(
                        "/selection-profiles/" + p.path("id").asText() + "/eligibility",
                        owner,
                        Map.of());
        assertThat(run.path("items"))
                .anySatisfy(
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
        assertThat(journey.path("decision").path("conditions").path("mode").asText())
                .isEqualTo("SBA_DEMO");
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
        ((ObjectNode) pre.path("request")).put("usageMode", "UNKNOWN");
        var incomplete = TestData.additions();
        ((ObjectNode) incomplete.path("financial")).remove("overdue");
        var app = ready(pre, incomplete);
        String id = app.path("id").asText();
        var first = submit(app, UUID.randomUUID().toString());
        var result = process(app);
        assertThat(result.path("decision").path("conditions").path("missingFields").toString())
                .contains("financial.overdue");
        var p = get("/selection-profiles/" + app.path("profileId").asText(), owner);
        p =
                send(
                        patch("/selection-profiles/" + p.path("id").asText()),
                        owner,
                        Map.of(
                                "expectedVersion",
                                p.path("rowVersion").asLong(),
                                "answers",
                                Map.of("request", Map.of("usageMode", "ONE_TIME"))),
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
        refreshed =
                send(
                        patch("/applications/" + id),
                        owner,
                        Map.of(
                                "expectedVersion",
                                refreshed.path("rowVersion").asLong(),
                                "answers",
                                Map.of("financial", Map.of("overdue", 0))),
                        200);
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
                                .path("request")
                                .path("usageMode")
                                .asText())
                .isEqualTo("UNKNOWN");
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
        assertThat(get("/forms/preliminary", owner).path("fields")).hasSize(15);
        assertThat(get("/forms/application", owner).path("fields")).hasSize(17);
        var scenarios = get("/demo/scenarios", owner).path("items");
        assertThat(scenarios).hasSize(8);
        for (var scenario : scenarios) {
            var preliminary = scenario.path("preliminaryAnswers");
            assertThat(preliminary.path("request").path("usageMode").asText())
                    .isEqualTo("ONE_TIME");
            new FormPolicy().validatePreliminary(preliminary);
        }
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

    ObjectNode rankingReply(JsonNode packet) {
        var reply = mapper.createObjectNode();
        reply.set("requestId", packet.path("requestId"));
        var metadata = reply.putObject("metadata");
        metadata.put("model", "TEST_FIXTURE_NOT_MODEL");
        metadata.put("modelVersion", "test-revision");
        metadata.put("queryTemplateVersion", "query-1");
        metadata.put("passageTemplateVersion", "passage-1");
        var results = reply.putArray("results");
        int rank = 1;
        for (var candidate : packet.path("candidates")) {
            var item = results.addObject();
            item.set("productId", candidate.path("productId"));
            item.set("productVersion", candidate.path("productVersion"));
            item.put("rank", rank);
            item.put("similarityScore", new java.math.BigDecimal("0.700000000123"));
            item.put("isRecommended", rank++ <= packet.path("topK").asInt());
            item.set("eligibilityStatus", candidate.path("eligibilityStatus"));
            item.set("pendingConditions", candidate.path("pendingConditions"));
        }
        return reply;
    }

    @Test
    void manualRankingPreservesConditionsAndReturnsAllCandidatesWithTopThreeHighlighted()
            throws Exception {
        var answers = TestData.preliminary();
        ((ObjectNode) answers.path("security")).put("guarantorReady", "DISCUSS");
        var profile = profile(answers);
        String base = "/selection-profiles/" + profile.path("id").asText();
        var run = post(base + "/eligibility", owner, Map.of());
        String route = base + "/recommendations/" + run.path("runId").asText();
        var packet = get(route + "/ranking-export", owner);
        assertThat(packet.path("candidates").size()).isGreaterThan(3);
        assertThat(packet.path("queryFields").path("request").has("amount")).isFalse();
        assertThat(packet.path("queryFields").path("security").path("guarantorReady").asText())
                .isEqualTo("DISCUSS");
        for (var candidate : packet.path("candidates"))
            assertThat(candidate.path("eligibilityStatus").asText()).isNotEqualTo("INELIGIBLE");
        var reply = rankingReply(packet);
        var imported = post(route + "/ranking-result", owner, reply);
        assertThat(imported.path("scoreMeaning").asText()).contains("NOT_APPROVAL");
        assertThat(imported.path("results")).hasSize(packet.path("candidates").size());
        for (int i = 0; i < imported.path("results").size(); i++) {
            var item = imported.path("results").get(i);
            var candidate = packet.path("candidates").get(i);
            assertThat(item.path("pendingConditions"))
                    .isEqualTo(candidate.path("pendingConditions"));
            assertThat(item.path("eligibilityStatus"))
                    .isEqualTo(candidate.path("eligibilityStatus"));
            assertThat(item.path("isRecommended").asBoolean()).isEqualTo(i < 3);
            assertThat(item.path("similarityScore").decimalValue())
                    .isEqualByComparingTo("0.700000000123");
        }
        assertThat(imported.path("results").get(0).path("pendingConditions")).isNotEmpty();
        assertThat(post(route + "/ranking-result", owner, reply)).isEqualTo(imported);
        ((ObjectNode) reply.path("results").get(0))
                .put("similarityScore", new java.math.BigDecimal("0.9"));
        send(
                org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post(
                        route + "/ranking-result"),
                owner,
                reply,
                409);
        var selected =
                send(
                        org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put(
                                base + "/selected-product"),
                        owner,
                        Map.of(
                                "expectedVersion",
                                profile.path("rowVersion").asLong(),
                                "runId",
                                run.path("runId").asText(),
                                "productVersionId",
                                packet.path("candidates").get(0).path("productVersion").asText()),
                        200);
        assertThat(get(route + "/ranking-result", owner).path("current").asBoolean()).isTrue();
        send(
                org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch(base),
                owner,
                Map.of(
                        "expectedVersion",
                        selected.path("rowVersion").asLong(),
                        "answers",
                        Map.of("request", Map.of("description", "Новая потребность"))),
                200);
        assertThat(get(route + "/ranking-result", owner).path("current").asBoolean()).isFalse();
        request(
                org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get(
                                route + "/ranking-export")
                        .header("Authorization", "Bearer " + owner),
                409);
        send(
                org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post(
                        route + "/ranking-result"),
                owner,
                reply,
                409);
        request(
                org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get(
                        route + "/ranking-result"),
                401);
        request(
                org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get(
                                route + "/ranking-result")
                        .header("Authorization", "Bearer " + bank),
                404);
    }

    @org.junit.jupiter.params.ParameterizedTest
    @org.junit.jupiter.params.provider.ValueSource(ints = {0, 1, 2, 3})
    void rankingAcceptsUpToThreeRecommendationsAndKeepsEveryCandidate(int recommended)
            throws Exception {
        var answers = TestData.preliminary();
        ((ObjectNode) answers.path("security")).put("guarantorReady", "DISCUSS");
        var profile = profile(answers);
        String base = "/selection-profiles/" + profile.path("id").asText();
        var run = post(base + "/eligibility", owner, Map.of());
        String route = base + "/recommendations/" + run.path("runId").asText();
        var packet = get(route + "/ranking-export", owner);
        assertThat(packet.path("candidates").size()).isGreaterThan(3);
        var reply = rankingReply(packet);
        for (int i = 0; i < reply.path("results").size(); i++)
            ((ObjectNode) reply.path("results").get(i)).put("isRecommended", i < recommended);
        var imported = post(route + "/ranking-result", owner, reply);
        assertThat(imported.path("results")).hasSize(packet.path("candidates").size());
        for (int i = 0; i < imported.path("results").size(); i++) {
            var item = imported.path("results").get(i);
            assertThat(item.path("isRecommended").asBoolean()).isEqualTo(i < recommended);
            assertThat(item.path("rank").asInt()).isEqualTo(i + 1);
            assertThat(item.path("pendingConditions"))
                    .isEqualTo(packet.path("candidates").get(i).path("pendingConditions"));
        }
        assertThat(post(route + "/ranking-result", owner, reply)).isEqualTo(imported);
    }

    @Test
    void rankingRejectsInvalidIdentityOrderScoreFlagsAndChangedApplicability() throws Exception {
        var a = TestData.preliminary();
        ((ObjectNode) a.path("security")).put("guarantorReady", "DISCUSS");
        var profile = profile(a);
        String base = "/selection-profiles/" + profile.path("id").asText();
        var run = post(base + "/eligibility", owner, Map.of());
        String route = base + "/recommendations/" + run.path("runId").asText();
        var packet = get(route + "/ranking-export", owner);
        var reply = rankingReply(packet);
        String path = route + "/ranking-result";
        var variants = new ArrayList<ObjectNode>();
        var bad = reply.deepCopy();
        ((ObjectNode) bad.path("results").get(0))
                .put("productVersion", UUID.randomUUID().toString());
        variants.add(bad);
        bad = reply.deepCopy();
        ((ObjectNode) bad.path("results").get(0)).put("rank", 2);
        variants.add(bad);
        bad = reply.deepCopy();
        ((com.fasterxml.jackson.databind.node.ArrayNode) bad.path("results")).remove(0);
        variants.add(bad);
        bad = reply.deepCopy();
        ((ObjectNode) bad.path("results").get(0)).put("similarityScore", 1.1);
        variants.add(bad);
        bad = reply.deepCopy();
        ((ObjectNode) bad.path("results").get(0)).put("similarityScore", -1.1);
        variants.add(bad);
        bad = reply.deepCopy();
        bad.put("requestId", UUID.randomUUID().toString());
        variants.add(bad);
        bad = reply.deepCopy();
        ((ObjectNode) bad.path("results").get(0)).put("rank", 1.5);
        variants.add(bad);
        bad = reply.deepCopy();
        ((ObjectNode) bad.path("results").get(0)).put("similarityScore", "0.5");
        variants.add(bad);
        bad = reply.deepCopy();
        ((ObjectNode) bad.path("results").get(0)).put("isRecommended", "true");
        variants.add(bad);
        bad = reply.deepCopy();
        ((ObjectNode) bad.path("results").get(0)).put("isRecommended", false);
        variants.add(bad);
        bad = reply.deepCopy();
        ((ObjectNode) bad.path("results").get(3)).put("isRecommended", true);
        variants.add(bad);
        bad = reply.deepCopy();
        ((ObjectNode) bad.path("results").get(0)).put("eligibilityStatus", "ELIGIBLE");
        variants.add(bad);
        bad = reply.deepCopy();
        ((ObjectNode) bad.path("results").get(0)).putArray("pendingConditions");
        variants.add(bad);
        bad = reply.deepCopy();
        ((ObjectNode) bad.path("results").get(0)).put("comment", "Not part of this contract");
        variants.add(bad);
        bad = reply.deepCopy();
        ((ObjectNode) bad.path("results").get(0)).put("similarityScore", -1);
        variants.add(bad); // Non-monotonic order.
        for (var variant : variants)
            send(
                    org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post(path),
                    owner,
                    variant,
                    400);
        assertThat(get(route + "/ranking-export", owner)).isEqualTo(packet);
    }

    @Test
    void emptyCandidateSetAcceptsEmptyRecsysResult() throws Exception {
        var answers = TestData.preliminary();
        ((ObjectNode) answers.path("request")).put("amount", "999999999999.00");
        var profile = profile(answers);
        String base = "/selection-profiles/" + profile.path("id").asText();
        var run = post(base + "/eligibility", owner, Map.of());
        String route = base + "/recommendations/" + run.path("runId").asText();
        var packet = get(route + "/ranking-export", owner);
        assertThat(packet.path("candidates")).isEmpty();
        var result = post(route + "/ranking-result", owner, rankingReply(packet));
        assertThat(result.path("results")).isEmpty();
        assertThat(result.path("requestId")).isEqualTo(packet.path("requestId"));
    }

    @Test
    void rankingRequiresUsageAnswerAndChecksNewEnumsAndDescription() throws Exception {
        var a = TestData.preliminary();
        ((ObjectNode) a.path("request")).remove("usageMode");
        var p = profile(a);
        String base = "/selection-profiles/" + p.path("id").asText();
        send(
                org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post(
                        base + "/eligibility"),
                owner,
                Map.of(),
                400);
        a = TestData.preliminary();
        ((ObjectNode) a.path("security")).put("collateralReady", true);
        send(
                org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post(
                        "/selection-profiles"),
                owner,
                Map.of("partyId", party, "answers", a),
                400);
        a = TestData.preliminary();
        ((ObjectNode) a.path("request")).put("description", "<b>HTML</b>");
        send(
                org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post(
                        "/selection-profiles"),
                owner,
                Map.of("partyId", party, "answers", a),
                400);
        a = TestData.preliminary();
        ((ObjectNode) a.path("request")).put("description", "x".repeat(501));
        send(
                org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post(
                        "/selection-profiles"),
                owner,
                Map.of("partyId", party, "answers", a),
                400);
        a = TestData.preliminary();
        ((ObjectNode) a.path("request")).put("usageMode", "UNKNOWN");
        ((ObjectNode) a.path("business")).putNull("sector");
        profile(a);
    }

    @Test
    void schemaEndpointsAndProductsExposeTheNewFieldContract() throws Exception {
        var preliminary = get("/forms/preliminary", owner);
        var application = get("/forms/application", owner);
        assertThat(preliminary.path("formVersion").asText()).isEqualTo("preliminary-2.0");
        assertThat(preliminary.path("fields").size()).isEqualTo(15);
        assertThat(application.path("formVersion").asText()).isEqualTo("application-3.0");
        assertThat(application.path("fields").size()).isEqualTo(17);
        assertThat(application.path("transferredFields").size()).isEqualTo(13);
        assertThat(application.path("fields").has("registration.registeredOn")).isFalse();
        var dictionaries = get("/forms/preliminary/dictionaries", owner);
        assertThat(dictionaries.path("sectors").size()).isEqualTo(7);
        assertThat(dictionaries.path("sectors").has("IT")).isTrue();
        assertThat(dictionaries.path("sectors").has("LOGISTICS")).isTrue();
        var p = get("/products/" + product, null);
        assertThat(p.path("type").asText()).isEqualTo("TERM_LOAN");
        assertThat(p.path("interestRateType").asText()).isEqualTo("FIXED");
        assertThat(p.path("usageModes").toString()).isEqualTo("[\"ONE_TIME\"]");
        assertThat(p.path("annualRatePct").isTextual()).isTrue();
        var catalog = get("/products?page=0&size=50", null).path("content");
        assertThat(catalog).hasSize(15);
        for (var item : catalog) {
            for (var purpose : item.path("purposes"))
                assertThat(RankingVocabulary.PURPOSES).containsKey(purpose.asText());
            if (Set.of("P10", "P15").contains(item.path("code").asText()))
                assertThat(item.path("purposes").toString())
                        .contains("DEVELOPMENT")
                        .doesNotContain("INVESTMENT");
        }
        assertThat(
                        db.sql(
                                        "SELECT count(*) FROM credit.credit_product_version WHERE allowed_purposes @> '[\"INVESTMENT\"]'::jsonb")
                                .query(Long.class)
                                .single())
                .isEqualTo(2L);
    }

    @Test
    void legacyProfileNeedsExplicitUpgradeAndOldRunRemainsUnchanged() throws Exception {
        var p = profile(TestData.preliminary());
        String base = "/selection-profiles/" + p.path("id").asText();
        var run = post(base + "/eligibility", owner, Map.of());
        var before = get(base + "/recommendations/" + run.path("runId").asText(), owner);
        db.sql(
                        "UPDATE credit.preliminary_profile SET form_version='preliminary-1.1',answers=jsonb_set(answers,'{registration,registeredOn}','\"2020-01-01\"'::jsonb) WHERE id=:id")
                .param("id", UUID.fromString(p.path("id").asText()))
                .update();
        var error =
                send(
                        org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post(
                                base + "/eligibility"),
                        owner,
                        Map.of(),
                        409);
        assertThat(error.path("code").asText()).isEqualTo("FORM_UPGRADE_REQUIRED");
        p =
                send(
                        patch(base),
                        owner,
                        Map.of(
                                "expectedVersion",
                                p.path("rowVersion").asLong(),
                                "answers",
                                Map.of()),
                        200);
        assertThat(p.path("formVersion").asText()).isEqualTo("preliminary-2.0");
        assertThat(p.path("answers").path("registration").has("registeredOn")).isFalse();
        assertThat(p.path("rowVersion").asLong()).isEqualTo(1);
        var after = get(base + "/recommendations/" + run.path("runId").asText(), owner);
        assertThat(after.path("items")).isEqualTo(before.path("items"));
        assertThat(after.path("current").asBoolean()).isFalse();
        post(base + "/eligibility", owner, Map.of());
    }

    @Test
    void legacyEditableApplicationUpgradesButExplicitUnknownSurvivesFurtherEdits()
            throws Exception {
        var app = ready(TestData.preliminary(), TestData.additions());
        String id = app.path("id").asText();
        var legacy = (ObjectNode) app.path("answers").deepCopy();
        ((ObjectNode) legacy.path("registration")).put("registeredOn", "2020-01-01");
        ((ObjectNode) legacy.path("business")).remove("sector");
        ((ObjectNode) legacy.path("security")).remove(List.of("collateralReady", "guarantorReady"));
        db.sql(
                        "UPDATE credit.loan_application SET form_version='application-2.1',draft_answers=CAST(:answers AS jsonb) WHERE id=:id")
                .param("id", UUID.fromString(id))
                .param("answers", mapper.writeValueAsString(legacy))
                .update();
        app =
                send(
                        patch("/applications/" + id),
                        owner,
                        Map.of(
                                "expectedVersion",
                                app.path("rowVersion").asLong(),
                                "answers",
                                Map.of()),
                        200);
        assertThat(app.path("answers").path("business").path("sector").asText()).isEqualTo("TRADE");
        assertThat(app.path("answers").path("security").path("guarantorReady").asText())
                .isEqualTo("YES");
        assertThat(app.path("answers").path("registration").has("registeredOn")).isFalse();
        var clear = mapper.readTree("{\"business\":{\"sector\":null}}");
        app =
                send(
                        patch("/applications/" + id),
                        owner,
                        Map.of(
                                "expectedVersion",
                                app.path("rowVersion").asLong(),
                                "answers",
                                clear),
                        200);
        app =
                send(
                        patch("/applications/" + id),
                        owner,
                        Map.of(
                                "expectedVersion",
                                app.path("rowVersion").asLong(),
                                "answers",
                                Map.of()),
                        200);
        assertThat(
                        app.path("answers").path("business").path("sector").isMissingNode()
                                || app.path("answers").path("business").path("sector").isNull())
                .isTrue();
        var validation = post("/applications/" + id + "/validate", owner, Map.of());
        assertThat(validation.path("value_status").path("business.sector").asText())
                .isEqualTo("UNKNOWN");
        assertThat(validation.path("review").path("kind").asText()).isEqualTo("REQUEST_INFO");
    }

    @Test
    void automaticSelectionWithoutRecsysKeepsCandidatesAndConditionsWithoutInventingRanking()
            throws Exception {
        var answers = TestData.preliminary();
        ((ObjectNode) answers.path("security")).put("guarantorReady", "DISCUSS");
        var p = profile(answers);
        String base = "/selection-profiles/" + p.path("id").asText();
        var selection = post(base + "/automatic-selection", owner, Map.of());
        assertThat(selection.path("rankingStatus").asText()).isEqualTo("NOT_CONFIGURED");
        assertThat(selection.path("current").asBoolean()).isTrue();
        assertThat(selection.path("results")).isNotEmpty();
        for (var item : selection.path("results")) {
            assertThat(item.has("similarityScore")).isFalse();
            assertThat(item.has("isRecommended")).isFalse();
            assertThat(item.path("eligibilityStatus").asText()).isIn("ELIGIBLE", "CONDITIONAL");
            assertThat(item.path("product").path("minAmount").isTextual()).isTrue();
        }
        assertThat(selection.path("results"))
                .anySatisfy(item -> assertThat(item.path("pendingConditions")).isNotEmpty());
        var retried =
                post(
                        base + "/recommendations/" + selection.path("runId").asText() + "/retry",
                        owner,
                        Map.of());
        assertThat(retried.path("rankingStatus").asText()).isEqualTo("NOT_CONFIGURED");
        assertThat(retried.path("results")).isEqualTo(selection.path("results"));
    }

    @Test
    void lowRevenueAndAbsurdAmountsNeverReturnCandidatesIncludingDirectApiCalls() throws Exception {
        for (String amount : List.of("1000000.00", "12121212121200000.00")) {
            var a = TestData.preliminary();
            ((ObjectNode) a.path("request")).put("amount", amount);
            ((ObjectNode) a.path("financial")).put("revenue", "10.00");
            var p = profile(a);
            String base = "/selection-profiles/" + p.path("id").asText();
            var result = post(base + "/automatic-selection", owner, Map.of());
            assertThat(result.path("results")).isEmpty();
            assertThat(result.path("rankingStatus").asText()).isEqualTo("EMPTY");
            assertThat(result.path("excluded")).hasSize(15);
            for (var excluded : result.path("excluded"))
                assertThat(excluded.path("reasons"))
                        .anySatisfy(
                                reason -> {
                                    assertThat(reason.path("code").asText())
                                            .isEqualTo("REVENUE_BELOW_MINIMUM");
                                    assertThat(reason.path("result").asText()).isEqualTo("FAIL");
                                });
            var choice =
                    send(
                            put(base + "/selected-product"),
                            owner,
                            Map.of(
                                    "expectedVersion",
                                    p.path("rowVersion").asLong(),
                                    "runId",
                                    result.path("runId").asText(),
                                    "productVersionId",
                                    product),
                            422);
            assertThat(choice.path("code").asText()).isEqualTo("PRODUCT_INELIGIBLE");
        }
    }

    @Test
    void suppliedRevenueNeedsAFullPeriodBeforeEligibilityButPartialDraftCanBeSaved()
            throws Exception {
        for (String field : List.of("periodFrom", "periodTo")) {
            var a = TestData.preliminary();
            ((ObjectNode) a.path("financial")).remove(field);
            var p = profile(a);
            var result =
                    send(
                            org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                                    .post(
                                            "/selection-profiles/"
                                                    + p.path("id").asText()
                                                    + "/automatic-selection"),
                            owner,
                            Map.of(),
                            400);
            assertThat(result.path("fields").toString()).contains("financial." + field);
        }
        var a = TestData.preliminary();
        ((ObjectNode) a.path("financial")).put("periodFrom", "2025-10-02");
        var p = profile(a);
        send(
                org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post(
                        "/selection-profiles/" + p.path("id").asText() + "/eligibility"),
                owner,
                Map.of(),
                400);
    }

    @Test
    void previousPolicyRunIsHistoricalAndCannotBeUsedToChooseExportOrCreateApplication()
            throws Exception {
        var p = select(profile(TestData.preliminary()));
        UUID previous = UUID.randomUUID();
        db.sql(
                        "INSERT INTO credit.recommendation_run(id,profile_id,profile_snapshot,model_version,policy_version) SELECT :id,profile_id,profile_snapshot,model_version,'eligibility-3.0' FROM credit.recommendation_run WHERE id=:source")
                .param("id", previous)
                .param("source", UUID.fromString(p.path("selectedRunId").asText()))
                .update();
        String base = "/selection-profiles/" + p.path("id").asText();
        assertThat(get(base + "/recommendations/" + previous, owner).path("current").asBoolean())
                .isFalse();
        send(
                put(base + "/selected-product"),
                owner,
                Map.of(
                        "expectedVersion",
                        p.path("rowVersion").asLong(),
                        "runId",
                        previous,
                        "productVersionId",
                        product),
                409);
        request(
                org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get(
                                base + "/recommendations/" + previous + "/ranking-export")
                        .header("Authorization", "Bearer " + owner),
                409);
        db.sql(
                        "UPDATE credit.preliminary_profile SET selected_recommendation_run_id=:run WHERE id=:id")
                .param("run", previous)
                .param("id", UUID.fromString(p.path("id").asText()))
                .update();
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
                        Map.of()),
                409);
    }

    @Test
    void scoringAuditLinksTheSelectedCounterofferAndKeepsBothInputs() throws Exception {
        SCORING.alternativeProbability = "0.12";
        var pre = TestData.preliminary();
        ((ObjectNode) pre.path("request")).put("amount", "2800000.00");
        ((ObjectNode) pre.path("financial")).put("revenue", "6000000.00");
        var additions = TestData.additions();
        ((ObjectNode) additions.path("financial")).put("monthlyDebtPayment", "130000.00");
        var app = ready(pre, additions);
        UUID id = UUID.fromString(app.path("id").asText());
        submit(app, UUID.randomUUID().toString());
        var result = process(app);
        assertThat(result.path("decision").path("kind").asText()).isEqualTo("COUNTEROFFERED");
        var assessments =
                db.sql(
                                "SELECT * FROM credit.assessment_run WHERE application_id=:app ORDER BY created_at,id")
                        .param("app", id)
                        .query()
                        .listOfRows();
        assertThat(assessments).hasSize(2);
        var selected =
                db.sql(
                                "SELECT r.output,r.input_manifest FROM credit.credit_decision d JOIN credit.assessment_run r ON r.id=d.assessment_id WHERE d.application_id=:app")
                        .param("app", id)
                        .query()
                        .singleRow();
        var selectedOutput = mapper.readTree(selected.get("output").toString());
        assertThat(selectedOutput.path("sbaDefaultProbability").decimalValue())
                .isEqualByComparingTo("0.12");
        assertThat(
                        result.path("decision")
                                .path("conditions")
                                .path("sbaDefaultProbability")
                                .decimalValue())
                .isEqualByComparingTo("0.12");
        assertThat(selectedOutput.path("warnings"))
                .isEqualTo(result.path("decision").path("conditions").path("warnings"));
        var selectedInput = mapper.readTree(selected.get("input_manifest").toString());
        assertThat(new java.math.BigDecimal(selectedInput.path("loanAmountUsd").asText()))
                .isEqualByComparingTo(
                        new java.math.BigDecimal(
                                        result.path("counteroffer")
                                                .path("alternative_terms")
                                                .path("amount")
                                                .asText())
                                .divide(ScoringExchange.FX, 2, java.math.RoundingMode.HALF_UP));
        for (var assessment : assessments) {
            var input = (ObjectNode) mapper.readTree(assessment.get("input_manifest").toString());
            input.remove("requestId");
            assertThat(assessment.get("input_sha256"))
                    .isEqualTo(Json.hash(TestData.JSON.canonical(input)));
        }
        assertThat(SCORING.calls.get()).isEqualTo(2);
    }

    @Test
    void historicalPolicyRevisionKeepsItsCheckVersionThroughDisbursement() throws Exception {
        var source = ready(TestData.preliminary(), TestData.additions());
        var sourceRevision = submit(source, UUID.randomUUID().toString());
        var row =
                db.sql("SELECT * FROM credit.application_revision WHERE id=:id")
                        .param("id", UUID.fromString(sourceRevision.path("revisionId").asText()))
                        .query()
                        .singleRow();
        var app = ready(TestData.preliminary(), TestData.additions());
        UUID id = UUID.fromString(app.path("id").asText()), revision = UUID.randomUUID();
        var snapshot = (ObjectNode) mapper.readTree(row.get("snapshot").toString());
        snapshot.put("policyVersion", LegacyDataPolicy.VERSION);
        var files =
                db.sql(
                                "SELECT id,sha256,type_code FROM credit.document_version WHERE application_id=:app ORDER BY id")
                        .param("app", id)
                        .query()
                        .listOfRows();
        snapshot.set("documents", mapper.valueToTree(files));
        String canonical = TestData.JSON.canonical(snapshot);
        db.sql(
                        "INSERT INTO credit.application_revision(id,application_id,revision_no,submitted_by,form_version,product_version_id,snapshot,snapshot_sha256,submission_evidence,submitted_at) VALUES (:id,:app,1,:user,:form,:product,CAST(:snapshot AS jsonb),:hash,CAST(:evidence AS jsonb),:at)")
                .param("id", revision)
                .param("app", id)
                .param("user", row.get("submitted_by"))
                .param("form", row.get("form_version"))
                .param("product", row.get("product_version_id"))
                .param("snapshot", canonical)
                .param("hash", Json.hash(canonical))
                .param("evidence", row.get("submission_evidence").toString())
                .param("at", row.get("submitted_at"))
                .update();
        for (var file : files)
            db.sql(
                            "INSERT INTO credit.revision_document(application_id,revision_id,document_version_id) VALUES (:app,:revision,:file)")
                    .param("app", id)
                    .param("revision", revision)
                    .param("file", file.get("id"))
                    .update();
        for (String gate : List.of("DECISION", "DISBURSEMENT"))
            db.sql(
                            "INSERT INTO credit.application_check_requirement(application_id,revision_id,check_code,rule_version,is_legal_gate,required_before,reason) VALUES (:app,:revision,:code,:version,false,:gate,'Historical fixture')")
                    .param("app", id)
                    .param("revision", revision)
                    .param("code", "DATA_POLICY_" + gate)
                    .param("version", LegacyDataPolicy.VERSION)
                    .param("gate", gate)
                    .update();
        db.sql(
                        "UPDATE credit.loan_application SET active_revision_id=:revision,status='SUBMITTED',last_changed_by=:user,last_change_reason='Historical fixture',row_version=row_version+1 WHERE id=:app")
                .param("revision", revision)
                .param("user", row.get("submitted_by"))
                .param("app", id)
                .update();
        var result = process(app);
        assertThat(result.path("decision").path("kind").asText()).isEqualTo("APPROVED");
        assertThat(result.path("decision").path("conditions").path("policyVersion").asText())
                .isEqualTo(LegacyDataPolicy.VERSION);
        post(
                "/applications/" + id + "/offers/accept",
                owner,
                Map.of("offerId", result.path("offer").path("id").asText(), "confirmed", true));
        post("/applications/" + id + "/contract/sign", owner, Map.of("confirmed", true));
        assertThat(
                        post(
                                        "/bank/applications/" + id + "/disburse",
                                        bank,
                                        Map.of("confirmed", true))
                                .path("application")
                                .path("status")
                                .asText())
                .isEqualTo("DISBURSED");
        assertThat(
                        db.sql(
                                        "SELECT DISTINCT rule_version FROM credit.check_run WHERE application_id=:app")
                                .param("app", id)
                                .query(String.class)
                                .list())
                .containsExactly(LegacyDataPolicy.VERSION);
        assertThat(
                        db.sql(
                                        "SELECT snapshot_sha256 FROM credit.application_revision WHERE id=:id")
                                .param("id", revision)
                                .query(String.class)
                                .single())
                .isEqualTo(Json.hash(canonical));
        assertThat(SCORING.calls.get()).isZero();
    }

    @Test
    @EnabledIfEnvironmentVariable(named = "RUN_REAL_SCORING_TESTS", matches = "1")
    void realScoringCompletesFourDecisionJourneys() throws Exception {
        var real =
                new ScoringGateway(
                        System.getenv("SCORING_ACCEPTANCE_URL"),
                        System.getenv("SCORING_ACCEPTANCE_KEY"),
                        TestData.JSON);
        org.mockito.Mockito.doAnswer(call -> real.evaluate(call.getArgument(0)))
                .when(scoringGateway)
                .evaluate(org.mockito.ArgumentMatchers.any());
        var outcomes = new ArrayList<Map<String, Object>>();
        try {
            for (String scenario :
                    List.of("APPROVED", "COUNTEROFFERED", "DECLINED", "REQUEST_INFO")) {
                var pre = TestData.preliminary();
                var additions = TestData.additions();
                ((ObjectNode) pre.path("request"))
                        .put(
                                "amount",
                                scenario.equals("COUNTEROFFERED") ? "1000000.00" : "300000.00");
                if (scenario.equals("DECLINED"))
                    ((ObjectNode) pre.path("request")).put("termMonths", 6);
                if (scenario.equals("COUNTEROFFERED")) {
                    ((ObjectNode) pre.path("financial")).put("revenue", "6000000.00");
                    ((ObjectNode) additions.path("financial"))
                            .put("monthlyDebtPayment", "170000.00");
                }
                if (scenario.equals("REQUEST_INFO"))
                    ((ObjectNode) additions.path("financial")).remove("monthlyDebtPayment");
                var app = ready(pre, additions);
                String id = app.path("id").asText();
                submit(app, UUID.randomUUID().toString());
                var result = process(app);
                assertThat(result.path("decision").path("kind").asText()).isEqualTo(scenario);
                var conditions = result.path("decision").path("conditions");
                if (!scenario.equals("REQUEST_INFO")) {
                    assertThat(conditions.path("modelVersion").asText())
                            .isEqualTo("sba-scoring-v1");
                    assertThat(conditions.path("warnings").toString())
                            .contains("RATE_OUT_OF_RANGE", "TERM_HISTORY_UNCONFIRMED");
                }
                var entry = new LinkedHashMap<String, Object>();
                entry.put("decision", scenario);
                if (conditions.has("sbaDefaultProbability"))
                    entry.put(
                            "probability", conditions.path("sbaDefaultProbability").decimalValue());
                entry.put(
                        "assessmentCount",
                        db.sql(
                                        "SELECT count(*) FROM credit.assessment_run WHERE application_id=:app")
                                .param("app", UUID.fromString(id))
                                .query(Integer.class)
                                .single());
                if (Set.of("APPROVED", "COUNTEROFFERED").contains(scenario)) {
                    if (scenario.equals("COUNTEROFFERED")) {
                        var offer = result.path("counteroffer");
                        result =
                                post(
                                        "/applications/" + id + "/counteroffers/accept",
                                        owner,
                                        Map.of(
                                                "proposalId",
                                                offer.path("id").asText(),
                                                "termsSha256",
                                                offer.path("termsSha256").asText(),
                                                "confirmed",
                                                true));
                    } else
                        result =
                                post(
                                        "/applications/" + id + "/offers/accept",
                                        owner,
                                        Map.of(
                                                "offerId",
                                                result.path("offer").path("id").asText(),
                                                "confirmed",
                                                true));
                    post(
                            "/applications/" + id + "/contract/sign",
                            owner,
                            Map.of("confirmed", true));
                    result =
                            post(
                                    "/bank/applications/" + id + "/disburse",
                                    bank,
                                    Map.of("confirmed", true));
                    assertThat(result.path("application").path("status").asText())
                            .isEqualTo("DISBURSED");
                    entry.put("finalStatus", "DISBURSED");
                }
                outcomes.add(entry);
            }
            Files.writeString(
                    Path.of("target/real-scoring-acceptance.json"),
                    mapper.writerWithDefaultPrettyPrinter()
                            .writeValueAsString(
                                    Map.of(
                                            "modelVersion",
                                            "sba-scoring-v1",
                                            "outcomes",
                                            outcomes)));
        } finally {
            org.mockito.Mockito.reset(scoringGateway);
        }
    }
}
