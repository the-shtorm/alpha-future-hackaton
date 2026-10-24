package ru.alphafuture.credit;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.annotation.JsonDeserialize;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.util.*;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;

/** Ручной JSON-обмен: проверяет чужой порядок и сохраняет исходные условия применимости. */
@RestController
class RankingExchange {
    static final String VERSION = "query-passage-mvp-2";
    static final int TOP_K = 3;
    static final Set<String> QUERY_FIELDS =
            Set.of(
                    "business.sector",
                    "request.purpose",
                    "request.usageMode",
                    "request.description",
                    "security.collateralReady",
                    "security.guarantorReady");

    record RankedItem(
            @NotNull UUID productId,
            @NotNull UUID productVersion,
            @NotNull @Positive @JsonDeserialize(using = RankingNumbers.Rank.class) Integer rank,
            @NotNull
                    @DecimalMin("-1")
                    @DecimalMax("1")
                    @JsonDeserialize(using = RankingNumbers.Similarity.class)
                    BigDecimal similarityScore,
            @NotNull @JsonDeserialize(using = RankingNumbers.Recommended.class)
                    Boolean isRecommended,
            @NotNull Eligibility.Status eligibilityStatus,
            @NotNull JsonNode pendingConditions) {}

    record Metadata(
            @NotBlank @Size(max = 120) String model,
            @NotBlank @Size(max = 120) String modelVersion,
            @NotBlank @Size(max = 120) String queryTemplateVersion,
            @NotBlank @Size(max = 120) String passageTemplateVersion) {}

    record RankingResponse(
            @NotNull UUID requestId,
            @NotNull @Valid Metadata metadata,
            @NotNull @Size(max = 1000) List<@NotNull @Valid RankedItem> results) {}

    record Candidate(
            UUID productId,
            UUID productVersion,
            Map<String, Object> product,
            Eligibility.Status eligibilityStatus,
            JsonNode pendingConditions,
            JsonNode checks) {}

    private final SelectionProfiles profiles;
    private final JdbcClient db;
    private final Json json;
    private final FormPolicy form;
    private final Catalog catalog;
    private final Access access;

    RankingExchange(
            SelectionProfiles profiles,
            JdbcClient db,
            Json json,
            FormPolicy form,
            Catalog catalog,
            Access access) {
        this.profiles = profiles;
        this.db = db;
        this.json = json;
        this.form = form;
        this.catalog = catalog;
        this.access = access;
    }

    /** Возвращает весь разрешённый набор; query/passages собирает команда Recsys. */
    @GetMapping("/selection-profiles/{id}/recommendations/{runId}/ranking-export")
    Map<String, Object> export(@PathVariable UUID id, @PathVariable UUID runId) {
        profiles.get(id);
        JsonNode snapshot = snapshot(id, runId);
        if (!FormPolicy.PRELIMINARY_VERSION.equals(snapshot.path("formVersion").asText()))
            throw new ApiFailure(409, "SELECTION_STALE", "Повторите подбор по новой схеме формы");
        form.validatePreliminary(snapshot.path("answers"));
        form.requireSelectionFields(snapshot.path("answers"));
        for (String path : List.of("request.purpose", "request.usageMode"))
            if (FormPolicy.text(snapshot.path("answers"), path) == null)
                throw ApiFailure.invalid(path, "Заполните поле перед передачей на ранжирование");
        if (!snapshot.path("semanticsVersion").asText().equals(ProductSemantics.VERSION))
            throw new ApiFailure(409, "SELECTION_STALE", "Повторите проверку по новому контракту");
        requireCurrent(id, runId, snapshot);
        var result = new LinkedHashMap<String, Object>();
        result.put("schemaVersion", VERSION);
        result.put("requestId", runId);
        result.put("profileId", id);
        result.put("profileVersion", snapshot.path("profileVersion"));
        result.put("topK", topK(snapshot));
        result.put("semanticsVersion", ProductSemantics.VERSION);
        result.put("profile", snapshot.path("answers"));
        result.put("queryFields", FormPolicy.project(snapshot.path("answers"), QUERY_FIELDS));
        result.put("dictionaries", new RankingVocabulary().dictionaries());
        result.put("candidates", candidates(runId, snapshot));
        result.put("scoreMeaning", "COSINE_SIMILARITY_NOT_APPROVAL_PROBABILITY");
        return result;
    }

    /** Полный результат, включая пустой список; повтор эквивалентного импорта безопасен. */
    @PostMapping("/selection-profiles/{id}/recommendations/{runId}/ranking-result")
    @Transactional
    Map<String, Object> accept(
            @PathVariable UUID id,
            @PathVariable UUID runId,
            @Valid @RequestBody RankingResponse response) {
        profiles.load(id, true, true);
        var snapshot = snapshot(id, runId);
        export(id, runId);
        if (!runId.equals(response.requestId()))
            throw ApiFailure.invalid(
                    "requestId", "Ответ не соответствует экспортированному запросу");
        var candidates = candidates(runId, snapshot);
        if (response.results().size() != candidates.size())
            throw ApiFailure.invalid("results", "Верните ровно всех переданных кандидатов");
        var byVersion = new HashMap<UUID, Candidate>();
        candidates.forEach(c -> byVersion.put(c.productVersion(), c));
        var sorted =
                response.results().stream().sorted(Comparator.comparing(RankedItem::rank)).toList();
        var seen = new HashSet<UUID>();
        BigDecimal previous = BigDecimal.ONE;
        int rank = 1;
        for (var item : sorted) {
            var candidate = byVersion.get(item.productVersion());
            if (candidate == null
                    || !seen.add(item.productVersion())
                    || item.rank() != rank
                    || !candidate.productId().equals(item.productId())
                    || item.similarityScore().compareTo(previous) > 0)
                throw ApiFailure.invalid(
                        "results", "Неверные идентификаторы, повторы, порядок или оценки сходства");
            if (item.isRecommended() != (rank <= topK(snapshot)))
                throw ApiFailure.invalid(
                        "results.isRecommended",
                        "Выделите ровно первые topK продуктов, максимум три");
            if (item.eligibilityStatus() != candidate.eligibilityStatus()
                    || !item.pendingConditions().isArray()
                    || !item.pendingConditions().equals(candidate.pendingConditions()))
                throw ApiFailure.invalid(
                        "results.pendingConditions/eligibilityStatus",
                        "Верните применимость и условия без изменений");
            previous = item.similarityScore();
            rank++;
        }
        JsonNode canonical =
                json.read(
                        json.write(
                                new RankingResponse(
                                        response.requestId(), response.metadata(), sorted)));
        var existing =
                db.sql("SELECT response FROM credit.manual_ranking_result WHERE run_id=:run")
                        .param("run", runId)
                        .query(String.class)
                        .optional();
        if (existing.isPresent()) {
            if (!json.read(existing.get()).equals(canonical))
                throw new ApiFailure(
                        409, "RANKING_ALREADY_IMPORTED", "Для подбора уже сохранён другой ответ");
            return result(id, runId);
        }
        db.sql(
                        "INSERT INTO credit.manual_ranking_result(run_id,response,imported_by) VALUES (:run,CAST(:response AS jsonb),:user)")
                .param("run", runId)
                .param("response", json.write(canonical))
                .param("user", access.user())
                .update();
        return result(id, runId);
    }

    /** Дополняет результат неизменёнными полями каталога; никаких текстовых комментариев Recsys. */
    @GetMapping("/selection-profiles/{id}/recommendations/{runId}/ranking-result")
    Map<String, Object> result(@PathVariable UUID id, @PathVariable UUID runId) {
        var profile = profiles.get(id);
        var snapshot = snapshot(id, runId);
        JsonNode response =
                json.read(
                        db.sql(
                                        "SELECT response FROM credit.manual_ranking_result WHERE run_id=:run")
                                .param("run", runId)
                                .query(String.class)
                                .optional()
                                .orElseThrow(ApiFailure::missing));
        var byVersion = new HashMap<String, Candidate>();
        candidates(runId, snapshot).forEach(c -> byVersion.put(c.productVersion().toString(), c));
        var results = new ArrayList<Map<String, Object>>();
        for (var item : response.path("results")) {
            var candidate = byVersion.get(item.path("productVersion").asText());
            var result = new LinkedHashMap<String, Object>();
            result.put("productId", candidate.productId());
            result.put("productVersion", candidate.productVersion());
            result.put("rank", item.path("rank").asInt());
            result.put("similarityScore", item.path("similarityScore"));
            result.put("isRecommended", item.path("isRecommended").asBoolean());
            result.put("eligibilityStatus", candidate.eligibilityStatus());
            result.put("pendingConditions", candidate.pendingConditions());
            result.put("product", candidate.product());
            result.put("checks", candidate.checks());
            results.add(result);
        }
        return Map.of(
                "requestId",
                runId,
                "profileVersion",
                snapshot.path("profileVersion"),
                "current",
                SelectionProfiles.isCurrent(profile, snapshot, runId),
                "ordering",
                "EXTERNAL_SIMILARITY",
                "scoreMeaning",
                "COSINE_SIMILARITY_NOT_APPROVAL_PROBABILITY",
                "metadata",
                response.path("metadata"),
                "results",
                results);
    }

    private int topK(JsonNode snapshot) {
        return Math.max(1, Math.min(3, snapshot.path("rankingTopK").asInt(TOP_K)));
    }

    private JsonNode snapshot(UUID id, UUID runId) {
        return json.read(
                db.sql(
                                "SELECT profile_snapshot FROM credit.recommendation_run WHERE id=:run AND profile_id=:profile")
                        .param("run", runId)
                        .param("profile", id)
                        .query(String.class)
                        .optional()
                        .orElseThrow(ApiFailure::missing));
    }

    private void requireCurrent(UUID id, UUID runId, JsonNode snapshot) {
        var profile = profiles.get(id);
        if (!SelectionProfiles.isCurrent(profile, snapshot, runId))
            throw new ApiFailure(
                    409, "SELECTION_STALE", "Форма изменилась; повторите проверку и экспорт");
        for (var candidate : candidates(runId, snapshot))
            if (!catalog.get(candidate.productId(), true)
                    .versionId()
                    .equals(candidate.productVersion()))
                throw new ApiFailure(
                        409, "CATALOG_STALE", "Условия продукта изменились; повторите подбор");
    }

    private List<Candidate> candidates(UUID runId, JsonNode snapshot) {
        var products = new HashMap<String, Map<String, Object>>();
        for (var node : snapshot.path("semanticProducts")) {
            var product = new LinkedHashMap<String, Object>();
            node.fields().forEachRemaining(e -> product.put(e.getKey(), e.getValue()));
            product.put("id", UUID.fromString(node.path("id").asText()));
            product.put("version", UUID.fromString(node.path("version").asText()));
            products.put(node.path("version").asText(), product);
        }
        return db.sql(
                        "SELECT explanation FROM credit.recommendation_item WHERE run_id=:run AND eligibility IN ('ELIGIBLE','CONDITIONAL') ORDER BY rank")
                .param("run", runId)
                .query(
                        (rs, n) -> {
                            var check = json.read(rs.getString(1));
                            var pending = json.mapper.createArrayNode();
                            for (var reason : check.path("reasons"))
                                if (!reason.path("result").asText().equals("PASS"))
                                    pending.add(reason);
                            var product = products.get(check.path("productVersionId").asText());
                            return new Candidate(
                                    (UUID) product.get("id"),
                                    (UUID) product.get("version"),
                                    product,
                                    Eligibility.Status.valueOf(check.path("status").asText()),
                                    pending,
                                    check.path("reasons"));
                        })
                .list();
    }
}
