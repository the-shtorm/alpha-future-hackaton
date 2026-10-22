package ru.alphafuture.credit;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import ru.alphafuture.credit.api.JsonSupport;

import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.Executors;

import static org.assertj.core.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@Testcontainers
@SpringBootTest
@org.springframework.test.context.ActiveProfiles("demo")
@AutoConfigureMockMvc
class ApiIntegrationTest {
    @Container static final PostgreSQLContainer<?> POSTGRES=new PostgreSQLContainer<>("postgres:17-bookworm")
        .withInitScript("db/api_test_roles.sql");
    @DynamicPropertySource static void database(DynamicPropertyRegistry r) {
        r.add("cabinet.demo-password",()->"test-demo-password-123");
        r.add("spring.datasource.url",POSTGRES::getJdbcUrl);
        r.add("spring.datasource.username",()->"credit_app");
        r.add("spring.datasource.password",()->"runtime-test-password");
        r.add("spring.flyway.url",POSTGRES::getJdbcUrl);
        r.add("spring.flyway.user",POSTGRES::getUsername);
        r.add("spring.flyway.password",POSTGRES::getPassword);
        r.add("spring.flyway.locations",()->"classpath:db/migration,classpath:db/demo");
        r.add("cabinet.documents-path",()->System.getProperty("java.io.tmpdir")+"/credit-api-tests-"+UUID.randomUUID());
    }
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;
    @Autowired JdbcClient db;
    @Autowired PasswordEncoder passwords;
    UUID user,party;
    String token;
    @BeforeEach void account() throws Exception {
        user=UUID.randomUUID();party=UUID.randomUUID();String login="test-"+user;
        db.sql("INSERT INTO credit.app_user(id,login,password_hash,display_name) VALUES (:id,:login,:hash,'Test')")
            .param("id",user).param("login",login).param("hash",passwords.encode("a-test-password")).update();
        db.sql("INSERT INTO credit.party(id,party_kind,name,tax_id) VALUES (:id,'LLC','Test','7707083893') ON CONFLICT (party_kind,tax_id) WHERE tax_id IS NOT NULL DO NOTHING")
            .param("id",party).update();
        party=db.sql("SELECT id FROM credit.party WHERE party_kind='LLC' AND tax_id='7707083893'").query(UUID.class).single();
        db.sql("INSERT INTO credit.party_membership(party_id,user_id,access_role) VALUES (:party,:user,'OWNER')")
            .param("party",party).param("user",user).update();
        token=perform(post("/auth/login").contentType("application/json").content(mapper.writeValueAsString(Map.of("login",login,"password","a-test-password"))),200).path("accessToken").asText();
    }
    @Test void catalogPagesFiltersAndRejectsInvalidInput() throws Exception {
        var first=perform(get("/products").param("size","4").param("sort","minAmount,asc"),200);
        assertThat(first.path("totalElements").asInt()).isEqualTo(15);
        assertThat(first.path("totalPages").asInt()).isEqualTo(4);
        assertThat(first.path("content").size()).isEqualTo(4);
        assertThat(first.path("content").get(0).has("policy")).isFalse();
        var next=perform(get("/products").param("page","1").param("size","4").param("sort","minAmount,asc"),200);
        var ids=new HashSet<String>();first.path("content").forEach(p->ids.add(p.path("id").asText()));
        next.path("content").forEach(p->assertThat(ids).doesNotContain(p.path("id").asText()));
        var filtered=perform(get("/products").param("amount","1000000.00").param("termMonths","12").param("purpose","WORKING_CAPITAL").param("collateralRequired","false"),200);
        assertThat(filtered.path("totalElements").asInt()).isPositive();
        for(var p:filtered.path("content")) {
            assertThat(p.path("minAmount").isTextual()).isTrue();
            assertThat(p.path("collateral").path("required").asBoolean()).isFalse();
        }
        perform(get("/products").param("size","51"),400);
        perform(get("/products").param("page","-1"),400);
        perform(get("/products").param("sort","name;drop table,asc"),400);
        perform(get("/products").param("amount","1.001"),400);
        String id=first.path("content").get(0).path("id").asText();
        assertThat(perform(get("/products/"+id),200).path("policy").isObject()).isTrue();
    }
    @Test void profileSecretOptimisticLockAndSourceProvenance() throws Exception {
        var created=perform(post("/selection-profiles").contentType("application/json").content("{\"answers\":{}}"),201);
        String id=created.path("profile").path("id").asText(),secret=created.path("accessToken").asText();
        perform(get("/selection-profiles/"+id),404);
        perform(get("/selection-profiles/"+id).header("X-Profile-Token","wrong"),404);
        var updated=perform(patch("/selection-profiles/"+id).header("X-Profile-Token",secret).contentType("application/json")
            .content("{\"expectedVersion\":0,\"answers\":{\"financial\":{\"revenue\":\"0.00\"}}}"),200);
        assertThat(updated.path("fieldSources").path("financial.revenue").path("verification_status").asText()).isEqualTo("DECLARED");
        perform(patch("/selection-profiles/"+id).header("X-Profile-Token",secret).contentType("application/json").content("{\"expectedVersion\":0,\"answers\":{}}"),409);
        perform(patch("/selection-profiles/"+id).header("X-Profile-Token",secret).contentType("application/json").content("{\"expectedVersion\":1,\"answers\":{\"verified\":true}}"),400);
        db.sql("UPDATE credit.preliminary_profile SET expires_at=now()-interval '1 second' WHERE id=:id").param("id",UUID.fromString(id)).update();
        perform(get("/selection-profiles/"+id).header("X-Profile-Token",secret),404);
    }
    @Test void missingDataIsConditionalAndRuleVersionsAreStored() throws Exception {
        var profile=createProfile("{}");String id=profile.path("id").asText();
        var evaluated=perform(post("/selection-profiles/"+id+"/eligibility").header("Authorization","Bearer "+token),200);
        assertThat(evaluated.path("items").size()).isEqualTo(15);
        for(var item:evaluated.path("items")) {
            assertThat(item.path("eligibility").asText()).isEqualTo("CONDITIONAL");
            assertThat(item.path("failed").isEmpty()).isTrue();
            assertThat(item.path("unconfirmed").isEmpty()).isFalse();
        }
        var run=db.sql("SELECT profile_snapshot,policy_version FROM credit.recommendation_run WHERE id=:id")
            .param("id",UUID.fromString(evaluated.path("runId").asText())).query().singleRow();
        assertThat(run.get("profile_snapshot").toString()).contains("rowVersion");
        assertThat(run.get("policy_version")).isEqualTo("catalog-rules-v1");
    }
    @Test void selectionInvalidatesOnEditAndHardFailureCannotBeSelected() throws Exception {
        var profile=createProfile(answers());String id=profile.path("id").asText(),product=productVersion();
        var result=perform(put("/selection-profiles/"+id+"/selected-product").header("Authorization","Bearer "+token).contentType("application/json")
            .content(mapper.writeValueAsString(Map.of("expectedVersion",0,"productVersionId",product))),200);
        assertThat(result.path("selectedProductVersionId").asText()).isEqualTo(product);
        result=perform(patch("/selection-profiles/"+id).header("Authorization","Bearer "+token).contentType("application/json")
            .content("{\"expectedVersion\":1,\"answers\":{\"request\":{\"amount\":\"1.00\"}}}"),200);
        assertThat(result.path("selectedProductVersionId").isNull()).isTrue();
        perform(put("/selection-profiles/"+id+"/selected-product").header("Authorization","Bearer "+token).contentType("application/json")
            .content(mapper.writeValueAsString(Map.of("expectedVersion",2,"productVersionId",product))),422);
    }
    @Test void validatesInnMoneyDatesAndRejectsTrustedClientFields() throws Exception {
        for(String answers:List.of("{\"registration\":{\"taxId\":\"7707083894\"}}","{\"request\":{\"amount\":1.2}}",
            "{\"financial\":{\"periodFrom\":\"2025-02-30\"}}","{\"registration\":{\"borrowerKind\":\"LLC\"},\"business\":{\"taxRegime\":\"PSN\"}}"))
            perform(post("/selection-profiles").contentType("application/json").content("{\"answers\":"+answers+"}"),400);
        perform(post("/selection-profiles").contentType("application/json").content("{\"answers\":{},\"createdBy\":\"fake\"}"),400);
        var found=perform(post("/business/lookup").contentType("application/json").content("{\"taxId\":\"7707083893\"}"),200);
        assertThat(found.path("isSimulated").asBoolean()).isTrue();
        perform(post("/business/lookup").contentType("application/json").content("{\"taxId\":\"0000000000\"}"),400);
    }
    @Test void fullSubmissionSealsSnapshotIsIdempotentAndDoesNotPretendAntivirusPassed() throws Exception {
        String id=createApplication();
        var validation=perform(post("/applications/"+id+"/validate").header("Authorization","Bearer "+token),200);
        assertThat(validation.path("validation").path("valid").asBoolean()).isFalse();
        perform(post("/applications/"+id+"/submit").header("Authorization","Bearer "+token).header("Idempotency-Key","first")
            .contentType("application/json").content("{\"expectedVersion\":0,\"confirmed\":true}"),422);
        var requirements=perform(get("/applications/"+id+"/requirements").header("Authorization","Bearer "+token),200);
        String versionId=null;
        String replacedId=null;
        int uploadedCount=0;
        for(var r:requirements) if (r.path("required_before").asText().equals("SUBMISSION")) {
            var upload=perform(multipart("/applications/"+id+"/documents").file(new MockMultipartFile("file","test.pdf","application/pdf","%PDF-1.7\n demo\n%%EOF".getBytes(StandardCharsets.UTF_8)))
                .param("requirementId",r.path("id").asText()).header("Authorization","Bearer "+token),201);
            versionId=upload.path("versionId").asText();
            uploadedCount++;
            if (replacedId==null) {
                replacedId=versionId;
                var replacement=perform(multipart("/applications/"+id+"/documents").file(new MockMultipartFile("file","updated.pdf","application/pdf","%PDF-1.7\n replacement\n%%EOF".getBytes(StandardCharsets.UTF_8)))
                    .param("requirementId",r.path("id").asText()).header("Authorization","Bearer "+token),201);
                assertThat(replacement.path("documentId").asText()).isEqualTo(upload.path("documentId").asText());
                assertThat(replacement.path("versionId").asText()).isNotEqualTo(replacedId);
            }
            assertThat(upload.path("antivirus").asText()).isEqualTo("UNKNOWN");
        }
        mvc.perform(get("/applications/"+id+"/documents/"+versionId).header("Authorization","Bearer "+token)).andExpect(status().isOk()).andExpect(header().string("Cache-Control","no-store"));
        var app=perform(get("/applications/"+id).header("Authorization","Bearer "+token),200);
        long version=app.path("rowVersion").asLong();String body=mapper.writeValueAsString(Map.of("expectedVersion",version,"confirmed",true));
        var submitted=perform(post("/applications/"+id+"/submit").header("Authorization","Bearer "+token).header("Idempotency-Key","success").contentType("application/json").content(body),200);
        var retry=perform(post("/applications/"+id+"/submit").header("Authorization","Bearer "+token).header("Idempotency-Key","success").contentType("application/json").content(body),200);
        assertThat(retry).isEqualTo(submitted);
        perform(post("/applications/"+id+"/submit").header("Authorization","Bearer "+token).header("Idempotency-Key","success").contentType("application/json")
            .content(mapper.writeValueAsString(Map.of("expectedVersion",version+1,"confirmed",true))),409);
        perform(patch("/applications/"+id).header("Authorization","Bearer "+token).contentType("application/json").content("{\"expectedVersion\":0,\"answers\":{}}"),409);
        var checked=perform(post("/applications/"+id+"/validate").header("Authorization","Bearer "+token),200);
        assertThat(checked.path("status").asText()).isEqualTo("NEEDS_INFO");
        assertThat(checked.toString()).contains("SCAN_PENDING");
        var results=perform(get("/applications/"+id+"/validation-results").header("Authorization","Bearer "+token),200);
        assertThat(results.get(0).path("revisionId").asText()).isEqualTo(submitted.path("revisionId").asText());
        assertThat(results.get(0).path("result").asText()).isEqualTo("REVIEW");
        var row=db.sql("SELECT snapshot,snapshot_sha256 FROM credit.application_revision WHERE id=:id")
            .param("id",UUID.fromString(submitted.path("revisionId").asText())).query().singleRow();
        assertThat(row.get("snapshot").toString()).contains("document_manifest","field_sources");
        assertThat(row.get("snapshot_sha256").toString()).hasSize(64);
        var oldSnapshot=mapper.readTree(row.get("snapshot").toString());
        assertThat(oldSnapshot.path("document_manifest").size()).isEqualTo(uploadedCount);
        assertThat(oldSnapshot.path("document_manifest").toString()).doesNotContain(replacedId);
        var canonical=new JsonSupport(mapper).canonical(oldSnapshot);
        assertThat(JsonSupport.hash(canonical)).isEqualTo(row.get("snapshot_sha256"));
        var history=perform(get("/applications/"+id+"/status").header("Authorization","Bearer "+token),200);
        assertThat(history.path("history").size()).isEqualTo(4);
        // Simulate a trusted scanner result, then exercise correction and a new submission.
        db.sql("""
            INSERT INTO credit.document_review(document_version_id,review_kind,result,engine_version,details)
            SELECT id,'ANTIVIRUS','PASS','test-scanner','{"is_simulated":true}' FROM credit.document_version WHERE application_id=:id
            """).param("id",UUID.fromString(id)).update();
        var changed=perform(patch("/applications/"+id).header("Authorization","Bearer "+token).contentType("application/json")
            .content(mapper.writeValueAsString(Map.of("expectedVersion",history.path("rowVersion").asLong(),"answers",Map.of("project",Map.of("repaymentSource","Updated revenue source"))))),200);
        var second=perform(post("/applications/"+id+"/submit").header("Authorization","Bearer "+token).header("Idempotency-Key","corrected").contentType("application/json")
            .content(mapper.writeValueAsString(Map.of("expectedVersion",changed.path("rowVersion").asLong(),"confirmed",true))),200);
        assertThat(second.path("revisionId")).isNotEqualTo(submitted.path("revisionId"));
        assertThat(perform(post("/applications/"+id+"/validate").header("Authorization","Bearer "+token),200).path("status").asText()).isEqualTo("ENRICHING");
        var unchanged=db.sql("SELECT snapshot_sha256 FROM credit.application_revision WHERE id=:id")
            .param("id",UUID.fromString(submitted.path("revisionId").asText())).query(String.class).single();
        assertThat(unchanged).isEqualTo(row.get("snapshot_sha256"));
        assertThat(perform(post("/applications/"+id+"/submit").header("Authorization","Bearer "+token).header("Idempotency-Key","success").contentType("application/json").content(body),200)).isEqualTo(submitted);
    }
    @Test void organizationIsolationAndReadOnlyMembership() throws Exception {
        String id=createApplication();
        db.sql("UPDATE credit.party_membership SET access_role='VIEWER' WHERE party_id=:party AND user_id=:user").param("party",party).param("user",user).update();
        perform(get("/applications/"+id).header("Authorization","Bearer "+token),200);
        perform(patch("/applications/"+id).header("Authorization","Bearer "+token).contentType("application/json").content("{\"expectedVersion\":0,\"answers\":{}}"),403);
        db.sql("UPDATE credit.party_membership SET revoked_at=now() WHERE party_id=:party AND user_id=:user").param("party",party).param("user",user).update();
        perform(get("/applications/"+id).header("Authorization","Bearer "+token),404);
        assertThat(perform(get("/applications").header("Authorization","Bearer "+token),200).path("content").isEmpty()).isTrue();
    }
    @Test void concurrentEditsHaveExactlyOneWinner() throws Exception {
        String id=createProfile("{}").path("id").asText();
        try(var executor=Executors.newFixedThreadPool(2)) {
            var tasks=new ArrayList<java.util.concurrent.Future<Integer>>();
            for(int i=0;i<2;i++) tasks.add(executor.submit(()->mvc.perform(patch("/selection-profiles/"+id).header("Authorization","Bearer "+token)
                .contentType("application/json").content("{\"expectedVersion\":0,\"answers\":{}}" )).andReturn().getResponse().getStatus()));
            assertThat(List.of(tasks.get(0).get(),tasks.get(1).get())).containsExactlyInAnyOrder(200,409);
        }
    }
    @Test void tokensCanBeRevokedAndDocsAreAvailable() throws Exception {
        perform(get("/me").header("Authorization","Bearer "+token),200);
        perform(post("/auth/logout").header("Authorization","Bearer "+token),200);
        perform(get("/me").header("Authorization","Bearer "+token),401);
        perform(get("/applications"),401);
        var spec=perform(get("/v3/api-docs"),200);
        assertThat(spec.path("paths").has("/products")).isTrue();
        assertThat(spec.at("/components/schemas/Product/properties/minAmount/type").asText()).isEqualTo("string");
        assertThat(spec.at("/components/schemas/ProductCard/properties/minAmount/type").asText()).isEqualTo("string");
        assertThat(spec.at("/components/schemas/Token/properties/accessToken/type").asText()).isEqualTo("string");
        assertThat(spec.path("paths").has("/applications/{id}/submit")).isTrue();
    }
    @Test void demoAccountIsUsableAndMalformedFilesAreRejected() throws Exception {
        var login=perform(post("/auth/login").contentType("application/json").content("{\"login\":\"demo-owner\",\"password\":\"test-demo-password-123\"}"),200);
        assertThat(perform(get("/me").header("Authorization","Bearer "+login.path("accessToken").asText()),200).path("parties").isEmpty()).isFalse();
        String id=createApplication();
        String requirement=perform(get("/applications/"+id+"/requirements").header("Authorization","Bearer "+token),200).get(0).path("id").asText();
        perform(multipart("/applications/"+id+"/documents").file(new MockMultipartFile("file","fake.pdf","application/pdf","untrusted text".getBytes(StandardCharsets.UTF_8)))
            .param("requirementId",requirement).header("Authorization","Bearer "+token),400);
    }
    private JsonNode createProfile(String answers) throws Exception {
        return perform(post("/selection-profiles").header("Authorization","Bearer "+token).contentType("application/json").content("{\"answers\":"+answers+"}"),201).path("profile");
    }
    private String productVersion() { return db.sql("SELECT v.id FROM credit.credit_product_version v JOIN credit.credit_product p ON p.id=v.product_id WHERE p.code='P01'").query(UUID.class).single().toString(); }
    private String createApplication() throws Exception {
        var profile=createProfile(answers());String profileId=profile.path("id").asText();
        perform(put("/selection-profiles/"+profileId+"/selected-product").header("Authorization","Bearer "+token).contentType("application/json")
            .content(mapper.writeValueAsString(Map.of("expectedVersion",0,"productVersionId",productVersion()))),200);
        return perform(post("/applications").header("Authorization","Bearer "+token).contentType("application/json")
            .content(mapper.writeValueAsString(Map.of("profileId",profileId,"partyId",party))),201).path("id").asText();
    }
    private String answers() { return """
        {"request":{"purpose":"WORKING_CAPITAL","amount":"1000000.00","termMonths":12},
         "registration":{"taxId":"7707083893","name":"Demo","borrowerKind":"LLC","registeredOn":"2020-01-01","country":"RU"},
         "business":{"actualStartedOn":"2020-01-01","region":"77","sector":"TRADE","taxRegime":"USN"},
         "financial":{"revenue":"24000000.00","periodFrom":"2025-10-01","periodTo":"2026-09-30"},
         "security":{"collateralReady":false,"guarantorReady":true},"project":{"repaymentSource":"Operating revenue"}}
        """; }
    private JsonNode perform(MockHttpServletRequestBuilder request,int status) throws Exception {
        var response=mvc.perform(request).andReturn().getResponse();
        assertThat(response.getStatus()).withFailMessage("Expected %s, got %s: %s",status,response.getStatus(),response.getContentAsString()).isEqualTo(status);
        return mapper.readTree(response.getContentAsString());
    }
}
