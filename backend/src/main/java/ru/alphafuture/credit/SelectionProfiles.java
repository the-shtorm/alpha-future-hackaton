package ru.alphafuture.credit;

import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.time.Instant;
import java.util.*;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;

/**
 * Предварительная форма 2.0, проверка продуктов и фиксация выбора; окончательные данные не
 * принимаются.
 */
@RestController
class SelectionProfiles {
    record Create(@NotNull UUID partyId, @NotNull JsonNode answers) {}

    record Patch(@NotNull @PositiveOrZero Long expectedVersion, @NotNull JsonNode answers) {}

    record Choose(
            @NotNull @PositiveOrZero Long expectedVersion,
            @NotNull UUID runId,
            @NotNull UUID productVersionId) {}

    record AcceptAlternative(@NotNull @PositiveOrZero Long expectedVersion) {}

    record Transfer(
            UUID id,
            UUID partyId,
            UUID productVersionId,
            long version,
            JsonNode answers,
            JsonNode sources,
            UUID runId) {}

    private final JdbcClient db;
    private final Access access;
    private final Json json;
    private final FormPolicy form;
    private final Catalog catalog;
    private final Eligibility eligibility;
    private final SelectionAlternatives alternatives;

    SelectionProfiles(
            JdbcClient db,
            Access access,
            Json json,
            FormPolicy form,
            Catalog catalog,
            Eligibility eligibility,
            SelectionAlternatives alternatives) {
        this.db = db;
        this.access = access;
        this.json = json;
        this.form = form;
        this.catalog = catalog;
        this.eligibility = eligibility;
        this.alternatives = alternatives;
    }

    @PostMapping("/selection-profiles")
    @Transactional
    Map<String, Object> create(@Valid @RequestBody Create body) {
        access.member(body.partyId(), true, false);
        form.validatePreliminary(body.answers());
        UUID id = UUID.randomUUID();
        db.sql(
                        "INSERT INTO credit.preliminary_profile(id,created_by,party_id,form_version,answers,field_sources) VALUES (:id,:user,:party,:form,CAST(:answers AS jsonb),CAST(:sources AS jsonb))")
                .param("id", id)
                .param("user", access.user())
                .param("party", body.partyId())
                .param("form", FormPolicy.PRELIMINARY_VERSION)
                .param("answers", json.write(body.answers()))
                .param(
                        "sources",
                        json.write(
                                sources(
                                        body.answers(),
                                        json.mapper.createObjectNode(),
                                        json.mapper.createObjectNode())))
                .update();
        return get(id);
    }

    @GetMapping("/selection-profiles/{id}")
    Map<String, Object> get(@PathVariable UUID id) {
        return response(load(id, false, false));
    }

    @PatchMapping("/selection-profiles/{id}")
    @Transactional
    Map<String, Object> patch(@PathVariable UUID id, @Valid @RequestBody Patch body) {
        var row = load(id, true, true);
        if (((Number) row.get("row_version")).longValue() != body.expectedVersion())
            throw ApiFailure.conflict();
        if (!body.answers().isObject())
            throw ApiFailure.invalid("answers", "Нужен объект изменений");
        var old = json.read(row.get("answers").toString());
        var answers =
                json.merge(FormPolicy.project(old, FormPolicy.PRELIMINARY_FIELDS), body.answers());
        form.validatePreliminary(answers);
        db.sql(
                        "UPDATE credit.preliminary_profile SET form_version=:form,answers=CAST(:answers AS jsonb),field_sources=CAST(:sources AS jsonb),selected_product_version_id=NULL,selected_recommendation_run_id=NULL,row_version=row_version+1 WHERE id=:id")
                .param("id", id)
                .param("form", FormPolicy.PRELIMINARY_VERSION)
                .param("answers", json.write(answers))
                .param(
                        "sources",
                        json.write(
                                sources(
                                        answers,
                                        old,
                                        json.read(row.get("field_sources").toString()))))
                .update();
        return get(id);
    }

    @PostMapping("/selection-profiles/{id}/eligibility")
    @Transactional
    Map<String, Object> evaluate(@PathVariable UUID id) {
        var row = load(id, true, true);
        var answers = json.read(row.get("answers").toString());
        requireCurrentSchema(row);
        form.validatePreliminary(answers);
        form.requireSelectionFields(answers);
        Instant asOf = Instant.now();
        var products = catalog.all();
        var results =
                products.stream()
                        .map(product -> eligibility.evaluate(product, answers, asOf))
                        .sorted(
                                Comparator.comparing(Eligibility.Result::status)
                                        .thenComparing(Eligibility.Result::productCode))
                        .toList();
        UUID run = UUID.randomUUID();
        var snapshot =
                Map.of(
                        "answers",
                        answers,
                        "profileVersion",
                        row.get("row_version"),
                        "formVersion",
                        FormPolicy.PRELIMINARY_VERSION,
                        "asOf",
                        asOf.toString(),
                        "products",
                        products,
                        "semanticsVersion",
                        ProductSemantics.VERSION,
                        "semanticProducts",
                        products.stream().map(ProductSemantics::describe).toList(),
                        "rankingTopK",
                        RankingExchange.TOP_K,
                        "alternatives",
                        alternatives.suggest(products, answers, asOf));
        db.sql(
                        "INSERT INTO credit.recommendation_run(id,profile_id,profile_snapshot,model_version,policy_version) VALUES (:id,:profile,CAST(:snapshot AS jsonb),'NOT_USED',:policy)")
                .param("id", run)
                .param("profile", id)
                .param("snapshot", json.write(snapshot))
                .param("policy", Eligibility.VERSION)
                .update();
        int rank = 1;
        for (var result : results)
            db.sql(
                            "INSERT INTO credit.recommendation_item(run_id,product_version_id,rank,score,eligibility,explanation) VALUES (:run,:version,:rank,NULL,:status,CAST(:explanation AS jsonb))")
                    .param("run", run)
                    .param("version", result.productVersionId())
                    .param("rank", rank++)
                    .param("status", result.status().name())
                    .param("explanation", json.write(result))
                    .update();
        return run(id, run);
    }

    @GetMapping("/selection-profiles/{id}/recommendations/{runId}")
    Map<String, Object> run(@PathVariable UUID id, @PathVariable UUID runId) {
        var profile = load(id, false, false);
        var row =
                db
                        .sql(
                                "SELECT profile_snapshot,created_at,policy_version FROM credit.recommendation_run WHERE id=:run AND profile_id=:profile")
                        .param("run", runId)
                        .param("profile", id)
                        .query()
                        .listOfRows()
                        .stream()
                        .findFirst()
                        .orElseThrow(ApiFailure::missing);
        JsonNode snapshot = json.read(row.get("profile_snapshot").toString());
        var items =
                db.sql(
                                "SELECT explanation FROM credit.recommendation_item WHERE run_id=:run ORDER BY rank")
                        .param("run", runId)
                        .query((rs, n) -> json.read(rs.getString(1)))
                        .list();
        return Map.of(
                "runId",
                runId,
                "profileId",
                id,
                "profileVersion",
                snapshot.path("profileVersion"),
                "asOf",
                snapshot.path("asOf"),
                "ordering",
                "ELIGIBILITY_THEN_PRODUCT_CODE",
                "personalRatingAvailable",
                false,
                "current",
                Eligibility.VERSION.equals(row.get("policy_version"))
                        && isCurrent(response(profile), snapshot, runId),
                "items",
                items);
    }

    @PutMapping("/selection-profiles/{id}/selected-product")
    @Transactional
    Map<String, Object> choose(@PathVariable UUID id, @Valid @RequestBody Choose body) {
        var row = load(id, true, true);
        requireCurrentSchema(row);
        requireCurrentRun(id, body.runId());
        if (((Number) row.get("row_version")).longValue() != body.expectedVersion())
            throw ApiFailure.conflict();
        var run =
                db
                        .sql(
                                "SELECT r.profile_snapshot,i.eligibility FROM credit.recommendation_run r JOIN credit.recommendation_item i ON i.run_id=r.id WHERE r.id=:run AND r.profile_id=:id AND i.product_version_id=:version")
                        .param("run", body.runId())
                        .param("id", id)
                        .param("version", body.productVersionId())
                        .query()
                        .listOfRows()
                        .stream()
                        .findFirst()
                        .orElseThrow(ApiFailure::missing);
        var snapshot = json.read(run.get("profile_snapshot").toString());
        if (snapshot.path("profileVersion").asLong() != body.expectedVersion()
                || !snapshot.path("answers").equals(json.read(row.get("answers").toString())))
            throw new ApiFailure(409, "SELECTION_STALE", "Повторите подбор для текущей формы");
        if (run.get("eligibility").equals("INELIGIBLE"))
            throw new ApiFailure(422, "PRODUCT_INELIGIBLE", "Продукт не соответствует форме");
        catalog.get(body.productVersionId(), true);
        db.sql(
                        "UPDATE credit.preliminary_profile SET selected_product_version_id=:version,selected_recommendation_run_id=:run,row_version=row_version+1 WHERE id=:id")
                .param("version", body.productVersionId())
                .param("run", body.runId())
                .param("id", id)
                .update();
        return get(id);
    }

    /** Применяет только сохранённый серверный вариант после явного выбора клиента. */
    @Transactional
    Map<String, Object> acceptAlternative(
            UUID id, UUID runId, UUID productVersionId, long expected) {
        var row = load(id, true, true);
        requireCurrentSchema(row);
        requireCurrentRun(id, runId);
        var snapshot =
                json.read(
                        db.sql(
                                        "SELECT profile_snapshot FROM credit.recommendation_run WHERE id=:run AND profile_id=:id")
                                .param("run", runId)
                                .param("id", id)
                                .query(String.class)
                                .single());
        if (((Number) row.get("row_version")).longValue() != expected
                || snapshot.path("profileVersion").asLong() != expected
                || !snapshot.path("answers").equals(json.read(row.get("answers").toString())))
            throw new ApiFailure(409, "SELECTION_STALE", "Повторите подбор для текущей формы");
        JsonNode alternative = null;
        for (var candidate : snapshot.path("alternatives"))
            if (candidate.path("productVersionId").asText().equals(productVersionId.toString()))
                alternative = candidate;
        if (alternative == null) throw ApiFailure.missing();
        var updated = patch(id, new Patch(expected, alternative.path("answersPatch")));
        var run = evaluate(id);
        // choose rechecks eligibility against a new snapshot of the active catalog.
        return choose(
                id,
                new Choose(
                        ((Number) updated.get("rowVersion")).longValue(),
                        (UUID) run.get("runId"),
                        productVersionId));
    }

    Transfer transfer(UUID id, long expected) {
        var row = load(id, true, true);
        requireCurrentSchema(row);
        if (((Number) row.get("row_version")).longValue() != expected) throw ApiFailure.conflict();
        if (row.get("selected_product_version_id") == null
                || row.get("selected_recommendation_run_id") == null)
            throw new ApiFailure(
                    422, "PRODUCT_REQUIRED", "Выберите продукт по актуальному подбору");
        requireCurrentRun(id, (UUID) row.get("selected_recommendation_run_id"));
        form.requireSelectionFields(json.read(row.get("answers").toString()));
        return new Transfer(
                id,
                (UUID) row.get("party_id"),
                (UUID) row.get("selected_product_version_id"),
                expected,
                json.read(row.get("answers").toString()),
                json.read(row.get("field_sources").toString()),
                (UUID) row.get("selected_recommendation_run_id"));
    }

    Map<String, Object> load(UUID id, boolean write, boolean lock) {
        var row =
                db
                        .sql(
                                "SELECT p.* FROM credit.preliminary_profile p WHERE p.id=:id AND EXISTS(SELECT 1 FROM credit.party_membership m WHERE m.party_id=p.party_id AND m.user_id=:user AND m.revoked_at IS NULL)"
                                        + (lock ? " FOR UPDATE OF p" : ""))
                        .param("id", id)
                        .param("user", access.user())
                        .query()
                        .listOfRows()
                        .stream()
                        .findFirst()
                        .orElseThrow(ApiFailure::missing);
        access.member((UUID) row.get("party_id"), write, false);
        return row;
    }

    /** Старые снимки доступны для истории, но не для нового выбора или выдачи заявки. */
    void requireCurrentRun(UUID id, UUID runId) {
        String version =
                db.sql(
                                "SELECT policy_version FROM credit.recommendation_run WHERE id=:run AND profile_id=:id")
                        .param("run", runId)
                        .param("id", id)
                        .query(String.class)
                        .optional()
                        .orElseThrow(ApiFailure::missing);
        if (!Eligibility.VERSION.equals(version))
            throw new ApiFailure(
                    409, "SELECTION_STALE", "Правила проверки изменились; повторите подбор");
    }

    private void requireCurrentSchema(Map<String, Object> row) {
        if (!FormPolicy.PRELIMINARY_VERSION.equals(row.get("form_version")))
            throw new ApiFailure(
                    409,
                    "FORM_UPGRADE_REQUIRED",
                    "Сохраните предварительную форму по новой схеме и повторите подбор");
    }

    static boolean isCurrent(Map<String, Object> profile, JsonNode snapshot, UUID runId) {
        long version = ((Number) profile.get("rowVersion")).longValue();
        long source = snapshot.path("profileVersion").asLong();
        return FormPolicy.PRELIMINARY_VERSION.equals(profile.get("formVersion"))
                && FormPolicy.PRELIMINARY_VERSION.equals(snapshot.path("formVersion").asText())
                && snapshot.path("answers").equals(profile.get("answers"))
                && (version == source
                        || version == source + 1 && runId.equals(profile.get("selectedRunId")));
    }

    private Map<String, Object> response(Map<String, Object> row) {
        var result = new LinkedHashMap<String, Object>();
        result.put("id", row.get("id"));
        result.put("partyId", row.get("party_id"));
        result.put("formVersion", row.get("form_version"));
        result.put("rowVersion", row.get("row_version"));
        result.put("answers", json.read(row.get("answers").toString()));
        result.put("fieldSources", json.read(row.get("field_sources").toString()));
        result.put(
                "value_status",
                form.statuses((JsonNode) result.get("answers"), FormPolicy.Stage.PRELIMINARY));
        result.put("selectedProductVersionId", row.get("selected_product_version_id"));
        result.put("selectedRunId", row.get("selected_recommendation_run_id"));
        return result;
    }

    private JsonNode sources(JsonNode answers, JsonNode old, JsonNode previous) {
        var result = json.mapper.createObjectNode();
        answers.fields()
                .forEachRemaining(
                        s ->
                                s.getValue()
                                        .fields()
                                        .forEachRemaining(
                                                f -> {
                                                    if (f.getValue().isNull()) return;
                                                    String key = s.getKey() + "." + f.getKey();
                                                    result.set(
                                                            key,
                                                            previous.has(key)
                                                                            && FormPolicy.value(
                                                                                            old,
                                                                                            key)
                                                                                    .equals(
                                                                                            f
                                                                                                    .getValue())
                                                                    ? previous.get(key)
                                                                    : json.tree(
                                                                            Map.of(
                                                                                    "source_code",
                                                                                    "MANUAL",
                                                                                    "verification_status",
                                                                                    "DECLARED",
                                                                                    "observed_at",
                                                                                    Instant.now()
                                                                                            .toString())));
                                                }));
        return result;
    }
}
