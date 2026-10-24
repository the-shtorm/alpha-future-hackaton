package ru.alphafuture.credit;

import com.fasterxml.jackson.databind.JsonNode;
import java.math.BigDecimal;
import java.time.*;
import java.util.*;
import org.springframework.stereotype.Component;

/** Схемы Preliminary Form 2.0 и полей Data Policy 3.0: 15 и 17 явных путей JSON. */
@Component
class FormPolicy {
    enum Type {
        MONEY,
        PERCENT,
        INTEGER,
        DATE,
        BOOLEAN,
        FRACTION,
        CODE,
        TEXT
    }

    enum ValueStatus {
        KNOWN,
        UNKNOWN,
        INVALID
    }

    enum Stage {
        PRELIMINARY,
        APPLICATION
    }

    static final String PRELIMINARY_VERSION = "preliminary-2.0";
    static final String APPLICATION_VERSION = "application-3.0";
    static final Set<String> TRANSFER_FIELDS =
            Set.of(
                    "request.amount",
                    "request.termMonths",
                    "request.purpose",
                    "registration.borrowerKind",
                    "business.sector",
                    "security.collateralReady",
                    "security.guarantorReady",
                    "business.actualStartedOn",
                    "business.taxRegime",
                    "business.mspRegistry",
                    "financial.revenue",
                    "financial.periodFrom",
                    "financial.periodTo");
    static final Set<String> APPLICATION_FIELDS;
    static final Set<String> PRELIMINARY_FIELDS;
    static final Map<String, Type> FIELDS;

    static {
        var application = new TreeSet<>(TRANSFER_FIELDS);
        application.addAll(
                List.of(
                        "financial.monthlyDebtPayment",
                        "financial.overdue",
                        "security.collateralValue",
                        "project.ownContributionPct"));
        APPLICATION_FIELDS = Collections.unmodifiableSet(application);
        var preliminary = new TreeSet<>(TRANSFER_FIELDS);
        preliminary.addAll(List.of("request.usageMode", "request.description"));
        PRELIMINARY_FIELDS = Collections.unmodifiableSet(preliminary);
        var fields = new TreeMap<String, Type>();
        for (var entry :
                Map.of(
                                Type.MONEY,
                                        List.of(
                                                "request.amount",
                                                "financial.revenue",
                                                "financial.monthlyDebtPayment",
                                                "security.collateralValue"),
                                Type.PERCENT, List.of("project.ownContributionPct"),
                                Type.INTEGER, List.of("request.termMonths"),
                                Type.DATE,
                                        List.of(
                                                "business.actualStartedOn",
                                                "financial.periodFrom",
                                                "financial.periodTo"),
                                Type.BOOLEAN, List.of("business.mspRegistry"),
                                Type.FRACTION, List.of("financial.overdue"),
                                Type.CODE,
                                        List.of(
                                                "request.purpose",
                                                "request.usageMode",
                                                "security.collateralReady",
                                                "security.guarantorReady",
                                                "registration.borrowerKind",
                                                "business.sector",
                                                "business.taxRegime"),
                                Type.TEXT, List.of("request.description"))
                        .entrySet())
            entry.getValue().forEach(key -> fields.put(key, entry.getKey()));
        FIELDS = Collections.unmodifiableMap(fields);
    }

    static Map<String, Type> fields(Stage stage) {
        var result = new TreeMap<String, Type>();
        (stage == Stage.APPLICATION ? APPLICATION_FIELDS : PRELIMINARY_FIELDS)
                .forEach(key -> result.put(key, FIELDS.get(key)));
        return Collections.unmodifiableMap(result);
    }

    void validatePreliminary(JsonNode answers) {
        validate(answers, Stage.PRELIMINARY);
    }

    void validate(JsonNode answers) {
        validate(answers, Stage.APPLICATION);
    }

    void validate(JsonNode answers, Stage stage) {
        if (answers == null || !answers.isObject())
            throw ApiFailure.invalid("answers", "Нужен объект ответов");
        answers.fields()
                .forEachRemaining(
                        section -> {
                            if (!section.getValue().isObject()
                                    || fields(stage).keySet().stream()
                                            .noneMatch(
                                                    key -> key.startsWith(section.getKey() + ".")))
                                throw ApiFailure.invalid(
                                        section.getKey(), "Неизвестный раздел формы");
                            section.getValue()
                                    .fields()
                                    .forEachRemaining(
                                            field -> {
                                                String path =
                                                        section.getKey() + "." + field.getKey();
                                                if (!fields(stage).containsKey(path))
                                                    throw ApiFailure.invalid(
                                                            path, "Неизвестное поле");
                                                if (!field.getValue().isNull())
                                                    validateValue(
                                                            path,
                                                            field.getValue(),
                                                            FIELDS.get(path));
                                            });
                        });
        String kind = text(answers, "registration.borrowerKind");
        if (kind != null && !Set.of("IP", "LLC").contains(kind))
            throw ApiFailure.invalid("registration.borrowerKind", "Укажите IP или LLC");
        String regime = text(answers, "business.taxRegime");
        if (regime != null
                && !Set.of("OSNO", "USN", "PSN", "AUSN", "NPD", "UNKNOWN").contains(regime))
            throw ApiFailure.invalid("business.taxRegime", "Неизвестный налоговый режим");
        if ("LLC".equals(kind) && Set.of("PSN", "NPD").contains(regime == null ? "" : regime))
            throw ApiFailure.invalid("business.taxRegime", "Налоговый режим несовместим с ООО");
        checkCode(answers, "request.usageMode", RankingVocabulary.USAGE_MODES.keySet());
        checkCode(answers, "request.purpose", RankingVocabulary.PURPOSES.keySet());
        var sectors = new HashSet<>(RankingVocabulary.SECTORS.keySet());
        sectors.add("UNKNOWN"); // Explicit unknown in drafts is never a known sector at scoring.
        checkCode(answers, "business.sector", sectors);
        for (String field : List.of("security.collateralReady", "security.guarantorReady"))
            checkCode(answers, field, RankingVocabulary.READINESS.keySet());
        String description = text(answers, "request.description");
        if (description != null
                && (description.length() > 500 || description.matches("(?s).*<[^>]*>.*")))
            throw ApiFailure.invalid("request.description", "Не более 500 символов, без HTML");
        LocalDate from = date(answers, "financial.periodFrom"),
                to = date(answers, "financial.periodTo");
        if (from != null && to != null && from.isAfter(to))
            throw ApiFailure.invalid("financial.periodTo", "Конец периода раньше начала");
    }

    /** Минимальные ответы нужны до фильтрации, но не для сохранения черновика. */
    void requireSelectionFields(JsonNode answers) {
        for (String path :
                List.of(
                        "registration.borrowerKind",
                        "request.purpose",
                        "request.amount",
                        "request.termMonths",
                        "request.usageMode"))
            if (text(answers, path) == null)
                throw ApiFailure.invalid(path, "Обязательное поле для подбора");
        if (money(answers, "financial.revenue") != null) {
            LocalDate from = date(answers, "financial.periodFrom"),
                    to = date(answers, "financial.periodTo");
            if (from == null)
                throw ApiFailure.invalid("financial.periodFrom", "Укажите начало периода выручки");
            if (to == null)
                throw ApiFailure.invalid("financial.periodTo", "Укажите конец периода выручки");
            if (from.getDayOfMonth() != 1)
                throw ApiFailure.invalid(
                        "financial.periodFrom",
                        "Период выручки должен начинаться с первого числа месяца");
            if (to.getDayOfMonth() != to.lengthOfMonth())
                throw ApiFailure.invalid(
                        "financial.periodTo",
                        "Период выручки должен заканчиваться последним днём месяца");
        }
    }

    private void checkCode(JsonNode answers, String field, Set<String> codes) {
        String value = text(answers, field);
        if (value != null && !codes.contains(value))
            throw ApiFailure.invalid(field, "Неизвестный код");
    }

    private void validateValue(String path, JsonNode value, Type type) {
        switch (type) {
            case MONEY, PERCENT -> {
                if (!value.isTextual()
                        || !value.asText().matches("(?:0|[1-9][0-9]{0,16})\\.[0-9]{2}"))
                    throw ApiFailure.invalid(
                            path,
                            "Нужна неотрицательная десятичная строка с 2 знаками после точки");
                var number = new BigDecimal(value.asText());
                if (path.equals("request.amount") && number.signum() == 0)
                    throw ApiFailure.invalid(path, "Нужно положительное значение");
                if (type == Type.PERCENT && number.compareTo(new BigDecimal("100")) > 0)
                    throw ApiFailure.invalid(path, "Процент должен быть от 0 до 100");
            }
            case FRACTION -> {
                if (!value.isNumber()
                        || value.decimalValue().signum() < 0
                        || value.decimalValue().compareTo(BigDecimal.ONE) > 0)
                    throw ApiFailure.invalid(path, "Нужна числовая доля от 0 до 1, не boolean");
            }
            case INTEGER -> {
                if (!value.isIntegralNumber()
                        || !value.canConvertToInt()
                        || value.asInt() < 0
                        || value.asInt() > 360
                        || path.equals("request.termMonths") && value.asInt() == 0)
                    throw ApiFailure.invalid(path, "Недопустимое целое число");
            }
            case BOOLEAN -> {
                if (!value.isBoolean()) throw ApiFailure.invalid(path, "Нужно true или false");
            }
            case DATE -> {
                try {
                    if (!value.isTextual()
                            || !value.asText().matches("[0-9]{4}-[0-9]{2}-[0-9]{2}")
                            || LocalDate.parse(value.asText())
                                    .isAfter(LocalDate.now(ZoneOffset.UTC)))
                        throw new IllegalArgumentException();
                } catch (Exception ex) {
                    throw ApiFailure.invalid(path, "Нужна прошедшая дата YYYY-MM-DD");
                }
            }
            case CODE, TEXT -> {
                if (!value.isTextual()
                        || value.asText().isBlank()
                        || value.asText().length() > 1000)
                    throw ApiFailure.invalid(path, "Нужна непустая строка до 1000 символов");
            }
        }
    }

    Map<String, ValueStatus> statuses(JsonNode answers) {
        return statuses(answers, Stage.APPLICATION);
    }

    Map<String, ValueStatus> statuses(JsonNode answers, Stage stage) {
        var result = new TreeMap<String, ValueStatus>();
        fields(stage)
                .forEach(
                        (key, type) -> {
                            var node = value(answers, key);
                            ValueStatus status = ValueStatus.UNKNOWN;
                            if (!node.isMissingNode()
                                    && !node.isNull()
                                    && !(type == Type.CODE && node.asText().equals("UNKNOWN"))) {
                                try {
                                    validate(project(answers, Set.of(key)), stage);
                                    status = ValueStatus.KNOWN;
                                } catch (ApiFailure ex) {
                                    status = ValueStatus.INVALID;
                                }
                            }
                            result.put(key, status);
                        });
        return result;
    }

    static com.fasterxml.jackson.databind.node.ObjectNode project(
            JsonNode source, Set<String> fields) {
        var result = com.fasterxml.jackson.databind.node.JsonNodeFactory.instance.objectNode();
        for (String path : fields) {
            var node = value(source, path);
            if (node.isMissingNode()) continue;
            var parts = path.split("\\.");
            var section =
                    result.has(parts[0])
                            ? (com.fasterxml.jackson.databind.node.ObjectNode) result.get(parts[0])
                            : result.putObject(parts[0]);
            section.set(parts[1], node.deepCopy());
        }
        return result;
    }

    static JsonNode selectionContext(JsonNode preliminary, JsonNode application) {
        var result = project(preliminary, PRELIMINARY_FIELDS);
        for (String path : TRANSFER_FIELDS) {
            var parts = path.split("\\.");
            var section =
                    result.has(parts[0])
                            ? (com.fasterxml.jackson.databind.node.ObjectNode) result.get(parts[0])
                            : result.putObject(parts[0]);
            var value = value(application, path);
            if (value.isMissingNode() || value.isNull()) section.remove(parts[1]);
            else section.set(parts[1], value.deepCopy());
        }
        return result;
    }

    static JsonNode value(JsonNode answers, String path) {
        var parts = path.split("\\.");
        return answers.path(parts[0]).path(parts[1]);
    }

    static String text(JsonNode answers, String path) {
        var value = value(answers, path);
        return value.isNull() || value.isMissingNode() ? null : value.asText();
    }

    static BigDecimal money(JsonNode answers, String path) {
        String value = text(answers, path);
        return value == null ? null : new BigDecimal(value);
    }

    static LocalDate date(JsonNode answers, String path) {
        String value = text(answers, path);
        return value == null ? null : LocalDate.parse(value);
    }
}
