package ru.alphafuture.credit;

import java.util.*;

/** Авторский смысловой слой только синтетического каталога, без расчёта текстов и эмбеддингов. */
class ProductSemantics {
    static final String VERSION = "synthetic-semantics-1";
    private static final Map<String, String> SCENARIOS =
            Map.ofEntries(
                    Map.entry("P01", "Разовое финансирование текущих задач и развития бизнеса"),
                    Map.entry("P02", "Разовое пополнение оборотных средств"),
                    Map.entry(
                            "P03",
                            "Повторяющееся использование и восстановление доступного лимита"),
                    Map.entry(
                            "P04", "Закупки с постепенным использованием невозобновляемого лимита"),
                    Map.entry("P05", "Покрытие нехватки средств на расчётном счёте"),
                    Map.entry("P06", "Финансирование сезонной потребности в оборотных средствах"),
                    Map.entry("P07", "Покупка оборудования с обеспечением"),
                    Map.entry("P08", "Покупка коммерческого транспорта с обеспечением"),
                    Map.entry("P09", "Покупка коммерческого помещения с обеспечением"),
                    Map.entry("P10", "Инвестиции и развитие под залог недвижимости"),
                    Map.entry("P11", "Финансирование исполнения контракта"),
                    Map.entry("P12", "Рефинансирование под залог недвижимости"),
                    Map.entry(
                            "P13",
                            "Небольшое разовое финансирование индивидуального предпринимателя"),
                    Map.entry("P14", "Пополнение оборотных средств продавца маркетплейса"),
                    Map.entry("P15", "Расширение производства и покупка оборудования"));

    static Map<String, Object> describe(Catalog.Product product) {
        String scenario = product.synthetic() ? SCENARIOS.get(product.code()) : null;
        if (scenario == null)
            throw new ApiFailure(
                    422, "SEMANTICS_REQUIRED", "Для продукта не согласован смысловой каталог");
        String type = product.type();
        if (type == null)
            throw new ApiFailure(422, "SEMANTICS_REQUIRED", "Неизвестный механизм финансирования");
        var result = new LinkedHashMap<String, Object>();
        result.put("id", product.id());
        result.put("version", product.versionId());
        result.put("code", product.code());
        result.put("name", product.name());
        result.put("type", type);
        result.put("purposes", product.purposes());
        result.put("usageModes", product.usageModes());
        result.put("targetScenario", scenario);
        result.put(
                "targetSectors",
                product.code().equals("P15") ? List.of("MANUFACTURING") : List.of());
        result.put(
                "specialization", product.code().equals("P14") ? "Продавцы маркетплейсов" : null);
        result.put(
                "collateralRequirement",
                product.policy().path("collateral").path("required").asBoolean()
                        ? "REQUIRED"
                        : "NONE");
        var guarantees = product.policy().path("guarantor");
        boolean any = false, all = true;
        for (var kind : product.borrowerKinds()) {
            String rule = guarantees.path(kind.asText()).asText();
            if (!rule.endsWith("_REQUIRED") && !rule.equals("NOT_REQUIRED_IN_DEMO"))
                throw new ApiFailure(
                        422, "SEMANTICS_REQUIRED", "Неизвестно требование к поручительству");
            boolean required = rule.endsWith("_REQUIRED");
            any |= required;
            all &= required;
        }
        result.put("guarantorRequirement", all ? "REQUIRED" : any ? "CONDITIONAL" : "NONE");
        result.put(
                "securityNote",
                any && !all
                        ? "Для ООО требуется поручительство контролирующего владельца; для ИП в DEMO не требуется"
                        : null);
        result.put("synthetic", true);
        return result;
    }
}
