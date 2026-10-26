package ru.alphafuture.credit;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Component;

/** Предлагает новые параметры запроса, сохраняя факты о бизнесе и требования продуктов. */
@Component
class SelectionAlternatives {
    record Change(String field, JsonNode from, JsonNode to, String message) {}

    record Alternative(
            UUID productVersionId,
            String productCode,
            JsonNode answersPatch,
            List<Change> changes,
            Eligibility.Result eligibility) {}

    private final Eligibility eligibility;
    private final Json json;

    SelectionAlternatives(Eligibility eligibility, Json json) {
        this.eligibility = eligibility;
        this.json = json;
    }

    List<Alternative> suggest(List<Catalog.Product> products, JsonNode answers, Instant asOf) {
        if (products.stream().anyMatch(p -> eligible(p, answers, asOf))) return List.of();
        var alternatives = new ArrayList<Alternative>();
        for (var product : products) {
            var proposed = (ObjectNode) answers.deepCopy();
            var request = (ObjectNode) proposed.path("request");
            var amount = FormPolicy.money(answers, "request.amount");
            if (amount.compareTo(new BigDecimal(product.minAmount())) < 0) continue;
            request.put(
                    "amount",
                    amount.min(new BigDecimal(product.maxAmount())).setScale(2).toPlainString());
            int term = FormPolicy.value(answers, "request.termMonths").asInt();
            request.put(
                    "termMonths",
                    Math.clamp(term, product.minTermMonths(), product.maxTermMonths()));
            String purpose = FormPolicy.text(answers, "request.purpose");
            if (!Eligibility.contains(product.purposes(), purpose)) {
                // Equipment/vehicle/property purchases can be considered as business development.
                // Never substitute an unrelated purpose such as refinancing or a cash gap.
                if (!Set.of("EQUIPMENT", "TRANSPORT", "COMMERCIAL_PROPERTY").contains(purpose)
                        || !Eligibility.contains(product.purposes(), "DEVELOPMENT")) continue;
                request.put("purpose", "DEVELOPMENT");
            }
            String usage = FormPolicy.text(answers, "request.usageMode");
            if (!"UNKNOWN".equals(usage) && !product.usageModes().contains(usage)) {
                if (product.usageModes().size() != 1) continue;
                request.put("usageMode", product.usageModes().getFirst());
            }
            var checked = eligibility.evaluate(product, proposed, asOf);
            if (checked.status() == Eligibility.Status.INELIGIBLE) continue;
            var patch = json.mapper.createObjectNode();
            var requestPatch = patch.putObject("request");
            var changes = new ArrayList<Change>();
            for (String key : List.of("amount", "termMonths", "purpose", "usageMode")) {
                JsonNode from = answers.path("request").path(key), to = request.path(key);
                boolean same =
                        key.equals("amount")
                                ? new BigDecimal(from.asText())
                                                .compareTo(new BigDecimal(to.asText()))
                                        == 0
                                : from.equals(to);
                if (same) continue;
                requestPatch.set(key, to);
                changes.add(
                        new Change(
                                "request." + key,
                                from,
                                to,
                                switch (key) {
                                    case "amount" -> "Сумма уменьшена до максимума продукта";
                                    case "termMonths" -> "Срок приведён к диапазону продукта";
                                    case "purpose" ->
                                            "Покупку можно рассмотреть в рамках развития бизнеса; подтвердите эту цель";
                                    default ->
                                            "Предлагается другой способ использования финансирования";
                                }));
            }
            if (!changes.isEmpty())
                alternatives.add(
                        new Alternative(
                                product.versionId(),
                                product.code(),
                                patch,
                                List.copyOf(changes),
                                checked));
        }
        return alternatives.stream()
                .sorted(
                        Comparator.comparingInt(
                                        (Alternative a) ->
                                                a.answersPatch().path("request").has("purpose")
                                                        ? 1
                                                        : 0)
                                .thenComparingInt(a -> a.changes().size())
                                .thenComparing(
                                        a ->
                                                FormPolicy.money(answers, "request.amount")
                                                        .subtract(
                                                                a.answersPatch()
                                                                                .path("request")
                                                                                .has("amount")
                                                                        ? FormPolicy.money(
                                                                                a.answersPatch(),
                                                                                "request.amount")
                                                                        : FormPolicy.money(
                                                                                answers,
                                                                                "request.amount")))
                                .thenComparing(Alternative::productCode))
                .limit(3)
                .toList();
    }

    private boolean eligible(Catalog.Product product, JsonNode answers, Instant asOf) {
        return eligibility.evaluate(product, answers, asOf).status()
                != Eligibility.Status.INELIGIBLE;
    }
}
