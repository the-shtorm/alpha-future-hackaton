package ru.alphafuture.credit;

import java.util.*;
import org.springframework.web.bind.annotation.*;

/** Общие машинные коды формы, каталога и ручного обмена с командой ранжирования. */
@RestController
class RankingVocabulary {
    static final Map<String, String> PURPOSES =
            Map.ofEntries(
                    Map.entry("WORKING_CAPITAL", "Пополнение оборотных средств"),
                    Map.entry("CASH_GAP", "Покрытие кассового разрыва"),
                    Map.entry("EQUIPMENT", "Покупка оборудования"),
                    Map.entry("TRANSPORT", "Покупка транспорта"),
                    Map.entry("COMMERCIAL_PROPERTY", "Покупка коммерческой недвижимости"),
                    Map.entry("CONTRACT_EXECUTION", "Исполнение контракта"),
                    Map.entry("REFINANCING", "Рефинансирование обязательств"),
                    Map.entry("DEVELOPMENT", "Развитие бизнеса"));
    static final Map<String, String> SECTORS =
            Map.of(
                    "TRADE",
                    "Торговля",
                    "MANUFACTURING",
                    "Производство",
                    "SERVICES",
                    "Услуги",
                    "IT",
                    "ИТ и разработка",
                    "CONSTRUCTION",
                    "Строительство",
                    "AGRICULTURE",
                    "Сельское хозяйство",
                    "LOGISTICS",
                    "Транспорт и логистика");
    static final Map<String, String> USAGE_MODES =
            Map.of(
                    "ONE_TIME",
                    "Одной суммой",
                    "IN_PARTS",
                    "Частями по мере необходимости",
                    "ACCOUNT_RESERVE",
                    "Резерв на расчётном счёте",
                    "UNKNOWN",
                    "Пока не определились");
    static final Map<String, String> READINESS =
            Map.of(
                    "YES",
                    "Готовы обсудить",
                    "NO",
                    "Не готовы",
                    "DISCUSS",
                    "Требуется обсуждение",
                    "UNKNOWN",
                    "Пока не знаем");

    @GetMapping("/forms/preliminary/dictionaries")
    Map<String, Object> dictionaries() {
        return Map.of(
                "version",
                "query-passage-mvp-2",
                "purposes",
                new TreeMap<>(PURPOSES),
                "sectors",
                new TreeMap<>(SECTORS),
                "usageModes",
                new TreeMap<>(USAGE_MODES),
                "readiness",
                new TreeMap<>(READINESS));
    }
}
