package ru.alphafuture.credit;

import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.Validator;
import java.util.*;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.web.bind.annotation.*;

/**
 * Пользовательский подбор: сервер вызывает Recsys, клиенту не нужно скачивать или загружать JSON.
 */
@RestController
class AutomaticSelection {
    private final SelectionProfiles profiles;
    private final RankingExchange ranking;
    private final RecsysGateway gateway;
    private final JdbcClient db;
    private final Access access;
    private final Json json;
    private final Catalog catalog;
    private final Validator validator;

    AutomaticSelection(
            SelectionProfiles profiles,
            RankingExchange ranking,
            RecsysGateway gateway,
            JdbcClient db,
            Access access,
            Json json,
            Catalog catalog,
            Validator validator) {
        this.profiles = profiles;
        this.ranking = ranking;
        this.gateway = gateway;
        this.db = db;
        this.access = access;
        this.json = json;
        this.catalog = catalog;
        this.validator = validator;
    }

    @PostMapping("/selection-profiles/{id}/automatic-selection")
    Map<String, Object> start(@PathVariable UUID id) {
        var run = profiles.evaluate(id);
        return retry(id, (UUID) run.get("runId"));
    }

    @PostMapping("/selection-profiles/{id}/recommendations/{runId}/retry")
    Map<String, Object> retry(@PathVariable UUID id, @PathVariable UUID runId) {
        profiles.load(id, true, false);
        var packet = ranking.export(id, runId);
        if (hasResult(runId)) return view(id, runId);
        var candidates = json.tree(packet.get("candidates"));
        if (candidates.isEmpty()) return record(id, runId, "EMPTY");
        if (!gateway.configured()) return record(id, runId, "NOT_CONFIGURED");
        // Only semantic query fields and applicability conditions cross this boundary.
        // Company identity, raw questionnaire finances and future risk/application data do not.
        var request = new LinkedHashMap<String, Object>();
        for (String key :
                List.of(
                        "schemaVersion",
                        "requestId",
                        "topK",
                        "semanticsVersion",
                        "queryFields",
                        "dictionaries")) request.put(key, packet.get(key));
        var safeCandidates = json.mapper.createArrayNode();
        for (var candidate : candidates) {
            var safe = candidate.deepCopy();
            ((com.fasterxml.jackson.databind.node.ObjectNode) safe).remove("checks");
            safeCandidates.add(safe);
        }
        request.put("candidates", safeCandidates);
        RankingExchange.RankingResponse response;
        try {
            JsonNode raw = gateway.rank(request);
            response = json.mapper.treeToValue(raw, RankingExchange.RankingResponse.class);
            if (response == null || !validator.validate(response).isEmpty())
                return record(id, runId, "INVALID_RESPONSE");
        } catch (RecsysGateway.Unavailable ex) {
            return record(id, runId, "UNAVAILABLE");
        } catch (Exception ex) {
            return record(id, runId, "INVALID_RESPONSE");
        }
        try {
            ranking.accept(id, runId, response);
        } catch (ApiFailure ex) {
            if (ex.status == 409) throw ex;
            if (ex.status == 400 || ex.status == 422) return record(id, runId, "INVALID_RESPONSE");
            throw ex;
        }
        return record(id, runId, "READY");
    }

    @GetMapping("/selection-profiles/{id}/recommendations/{runId}/view")
    Map<String, Object> view(@PathVariable UUID id, @PathVariable UUID runId) {
        var checked = profiles.run(id, runId);
        var snapshot =
                json.read(
                        db.sql(
                                        "SELECT profile_snapshot FROM credit.recommendation_run WHERE id=:run AND profile_id=:profile")
                                .param("run", runId)
                                .param("profile", id)
                                .query(String.class)
                                .single());
        var products = new HashMap<String, Catalog.Product>();
        for (var node : snapshot.path("products")) {
            var product = catalog.frozen(node);
            products.put(product.versionId().toString(), product);
        }
        boolean ready = hasResult(runId);
        var source =
                ready
                        ? json.tree(ranking.result(id, runId).get("results"))
                        : json.tree(checked.get("items"));
        var results = new ArrayList<Map<String, Object>>();
        var excluded = new ArrayList<JsonNode>();
        for (var item : source) {
            String status = item.path(ready ? "eligibilityStatus" : "status").asText();
            if (status.equals("INELIGIBLE")) {
                excluded.add(item);
                continue;
            }
            String version = item.path(ready ? "productVersion" : "productVersionId").asText();
            var product = products.get(version);
            var pending = json.mapper.createArrayNode();
            if (ready)
                pending.addAll(
                        (com.fasterxml.jackson.databind.node.ArrayNode)
                                item.path("pendingConditions"));
            else
                for (var reason : item.path("reasons"))
                    if (!reason.path("result").asText().equals("PASS")) pending.add(reason);
            var result = new LinkedHashMap<String, Object>();
            result.put("productId", product.id());
            result.put("productVersion", product.versionId());
            result.put("product", product);
            result.put("eligibilityStatus", status);
            result.put("pendingConditions", pending);
            if (ready) {
                result.put("rank", item.path("rank"));
                result.put("isRecommended", item.path("isRecommended"));
                result.put("similarityScore", item.path("similarityScore"));
            }
            results.add(result);
        }
        if (ready)
            for (var item : json.tree(checked.get("items")))
                if (item.path("status").asText().equals("INELIGIBLE")) excluded.add(item);
        String status =
                ready
                        ? "READY"
                        : db.sql(
                                        "SELECT status FROM credit.recommendation_attempt WHERE run_id=:run ORDER BY created_at DESC,id DESC LIMIT 1")
                                .param("run", runId)
                                .query(String.class)
                                .optional()
                                .orElse(results.isEmpty() ? "EMPTY" : "NOT_REQUESTED");
        return Map.of(
                "profileId",
                id,
                "runId",
                runId,
                "requestId",
                runId,
                "current",
                checked.get("current"),
                "rankingStatus",
                status,
                "results",
                results,
                "excluded",
                excluded,
                "asOf",
                snapshot.path("asOf"));
    }

    @GetMapping("/selections")
    Map<String, Object> list() {
        var items =
                db.sql(
                                "SELECT p.id,p.party_id,p.answers,p.row_version,p.created_at,c.name AS company_name,r.id AS run_id FROM credit.preliminary_profile p JOIN credit.party c ON c.id=p.party_id LEFT JOIN LATERAL(SELECT id FROM credit.recommendation_run WHERE profile_id=p.id ORDER BY created_at DESC,id DESC LIMIT 1) r ON true WHERE EXISTS(SELECT 1 FROM credit.party_membership m WHERE m.party_id=p.party_id AND m.user_id=:user AND m.revoked_at IS NULL) ORDER BY p.created_at DESC,p.id LIMIT 50")
                        .param("user", access.user())
                        .query()
                        .listOfRows();
        return Map.of(
                "items",
                items.stream()
                        .map(
                                row -> {
                                    var result = new LinkedHashMap<String, Object>(row);
                                    result.put("answers", json.read(row.get("answers").toString()));
                                    return result;
                                })
                        .toList());
    }

    private boolean hasResult(UUID runId) {
        return db.sql("SELECT EXISTS(SELECT 1 FROM credit.manual_ranking_result WHERE run_id=:run)")
                .param("run", runId)
                .query(Boolean.class)
                .single();
    }

    private Map<String, Object> record(UUID id, UUID runId, String status) {
        db.sql(
                        "INSERT INTO credit.recommendation_attempt(run_id,status,requested_by) VALUES (:run,:status,:user)")
                .param("run", runId)
                .param("status", status)
                .param("user", access.user())
                .update();
        return view(id, runId);
    }
}
