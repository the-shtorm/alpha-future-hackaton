"""New synthetic train families and a fresh final test; labels fixed before training."""

import json

from app.core.config import ROOT
from scripts.build_calibration_set import PURPOSE, REL

BUSINESSES = [
    ("TRADE", "дистрибьютор оптических аксессуаров"),
    ("TRADE", "магазин электротоваров"),
    ("TRADE", "продавец туристического инвентаря"),
    ("SERVICES", "ателье ремонта обуви"),
    ("SERVICES", "сервис обслуживания бассейнов"),
    ("SERVICES", "студия перевода документов"),
    ("IT", "разработчик систем складского учёта"),
    ("IT", "студия мобильных приложений"),
    ("MANUFACTURING", "производитель картонной тары"),
    ("MANUFACTURING", "мастерская обработки мрамора"),
    ("MANUFACTURING", "фабрика светильников"),
    ("AGRICULTURE", "производитель микрозелени"),
    ("AGRICULTURE", "рыбоводческое хозяйство"),
    ("CONSTRUCTION", "монтажник вентиляционных систем"),
    ("CONSTRUCTION", "подрядчик фасадных работ"),
    ("LOGISTICS", "оператор холодных складов"),
    ("LOGISTICS", "экспедитор сборных грузов"),
    ("TRADE", "магазин товаров для садовых прудов"),
    ("SERVICES", "мастерская музыкальных инструментов"),
    ("MANUFACTURING", "цех металлоизделий"),
]
TASKS = {
    "ordinary": [
        "Нужен обычный разовый кредит на текущие закупки. Сезонности нет, на маркетплейсах не продаём.",
        "Одна закупка для текущей деятельности, без сезонного проекта и без интернет-маркетплейсов.",
    ],
    "seasonal": [
        "Финансируем сезонную потребность в оборотных средствах до периода максимальных продаж.",
        "Текущие закупки нужны перед сезонным пиком, выручка поступит в течение высокого сезона.",
    ],
    "marketplace": [
        "Работаем продавцом на маркетплейсе больше года, пополняем товарные запасы для площадки.",
        "Основные продажи идут через Ozon и Wildberries, нужна одна закупка для интернет-площадок.",
    ],
    "revolving": [
        "Нужна линия частями с восстановлением лимита после погашения, чтобы использовать деньги повторно.",
        "Погашаем долг и снова выбираем возвращённые суммы из возобновляемого кредитного лимита.",
    ],
    "nonrevolving": [
        "Закупки выполняются этапами из невозобновляемого лимита, погашенные суммы не выбираем повторно.",
        "Нужны транши под один план закупок, без восстановления кредитного лимита после погашения.",
    ],
    "overdraft": [
        "Нужен резерв расчётного счёта, чтобы покрывать краткие кассовые разрывы до оплаты покупателей.",
        "Временная нехватка денег на счёте до поступления выручки; ищем овердрафт для обязательных платежей.",
    ],
    "equipment": [
        "Покупаем профессиональное оборудование для работы, а не транспорт и не помещение.",
        "Расширяем деятельность покупкой оборудования одним платежом, готовы обсудить обеспечение.",
    ],
    "transport": [
        "Приобретаем коммерческий грузовой автомобиль для бизнеса, не производственный станок.",
        "Нужна покупка коммерческого транспорта с обеспечением, а не кредит на текущие закупки.",
    ],
    "property": [
        "Покупаем нежилое коммерческое помещение для работы, не оборудование и не автомобиль.",
        "Выкупаем помещение вместо аренды, финансируем именно приобретение недвижимости.",
    ],
    "investment": [
        "Инвестируем в развитие и расширение бизнеса под залог собственного коммерческого здания.",
        "Нужно долгосрочное финансирование развития под залог недвижимости, не пополнение оборотных средств.",
    ],
    "contract": [
        "Деньги нужны для исполнения уже заключённого контракта на поставку или услуги.",
        "Финансируем выполнение обязательств по подписанному контракту, а не покупку основных средств.",
    ],
    "refinance": [
        "Хотим заменить имеющиеся кредиты одним новым кредитом под залог недвижимости.",
        "Нужно рефинансирование действующей задолженности с обеспечением, новых закупок не планируем.",
    ],
    "ip": [
        "Работаем как ИП, нужен небольшой разовый кредит на обычные текущие расходы.",
        "Индивидуальному предпринимателю требуется небольшая сумма на разовую закупку для деятельности.",
    ],
    "no_relevant": [
        "Кредит не нужен, ищем только банковское обслуживание без заёмных денег.",
        "Не собираемся брать кредит. Требуется только страхование имущества, без финансирования.",
    ],
    "restricted_catalog": [
        "Нужен восстановляемый лимит для многократного использования денег. Невозобновляемая линия не подходит.",
        "Обычная разовая закупка без сезонности и продаж через маркетплейсы, специализированные продукты не подходят.",
    ],
}
FINAL_CASES = {
    "ordinary": [
        (
            "CONSTRUCTION",
            "Фирма по монтажу лифтов оплачивает одну поставку расходников. Нужны обычные оборотные средства, продажи на площадках и сезонность отсутствуют.",
        ),
        (
            "TRADE",
            "Оптовик медицинского текстиля делает одну обычную закупку. Сезонного пика нет и через маркетплейсы не торгуем.",
        ),
    ],
    "seasonal": [
        (
            "SERVICES",
            "Оператор открытого катка финансирует текущие приготовления перед зимой, основные поступления будут в зимний сезон.",
        ),
        (
            "AGRICULTURE",
            "Тепличному хозяйству нужны оборотные средства на сезонные закупки до массового сбора урожая.",
        ),
    ],
    "marketplace": [
        (
            "TRADE",
            "Продаём комплектующие для робототехники через маркетплейс больше года. Кредит нужен для товарного запаса на площадке.",
        ),
        (
            "MANUFACTURING",
            "Изготавливаем деревянные головоломки и продаём через Wildberries, пополняем запасы для этого канала продаж.",
        ),
    ],
    "revolving": [
        (
            "TRADE",
            "Торговец упаковочными материалами хочет брать деньги небольшими частями, возвращать и опять использовать восстановленный лимит.",
        ),
        (
            "SERVICES",
            "Хостелу нужен оборотный лимит, доступная сумма которого восстанавливается после погашения и может выбираться снова.",
        ),
    ],
    "nonrevolving": [
        (
            "MANUFACTURING",
            "Для одного заказа приобретаем сырьё этапами. После возврата денег повторная выборка не нужна, ищем невозобновляемую линию.",
        ),
        (
            "CONSTRUCTION",
            "Поставки материалов для реконструкции идут по очереди, деньги берём траншами из уменьшающегося невозобновляемого лимита.",
        ),
    ],
    "overdraft": [
        (
            "IT",
            "Агентство цифровой аналитики платит сотрудникам до поступления оплаты заказчика. Нужна подстраховка расчётного счёта на несколько дней.",
        ),
        (
            "LOGISTICS",
            "Оператор почтовых отправлений покрывает короткие разрывы между текущими платежами и выручкой, нужен резерв на счёте.",
        ),
    ],
    "equipment": [
        (
            "MANUFACTURING",
            "Фабрика мороженого расширяет мощности покупкой промышленного морозильного оборудования.",
        ),
        (
            "SERVICES",
            "Офтальмологический кабинет покупает диагностический прибор, помещение и транспорт покупать не собираемся.",
        ),
    ],
    "transport": [
        (
            "SERVICES",
            "Мобильная лаборатория приобретает коммерческий фургон для выездов к клиентам, готовы обсуждать обеспечение.",
        ),
        (
            "AGRICULTURE",
            "Плодовый кооператив покупает коммерческий грузовой автомобиль для перевозки продукции.",
        ),
    ],
    "property": [
        (
            "IT",
            "Студия компьютерной графики выкупает нежилой офис. Требуется финансирование покупки коммерческой недвижимости.",
        ),
        (
            "SERVICES",
            "Школа плавания приобретает коммерческое помещение для занятий, а не инвентарь или транспорт.",
        ),
    ],
    "investment": [
        (
            "LOGISTICS",
            "Развиваем сеть перевалочных пунктов, ищем инвестиционный кредит под залог принадлежащего компании здания.",
        ),
        (
            "MANUFACTURING",
            "Предприятие керамических покрытий расширяет производство и финансирует новые производственные мощности.",
        ),
    ],
    "contract": [
        (
            "AGRICULTURE",
            "Поставщик кормов финансирует исполнение подписанного контракта на поставку животноводческой ферме.",
        ),
        (
            "SERVICES",
            "Охранная компания выполняет заключённый контракт на обслуживание объектов, деньги нужны на исполнение обязательств.",
        ),
    ],
    "refinance": [
        (
            "MANUFACTURING",
            "Производитель фильтров хочет рефинансировать старые кредиты под залог собственного помещения, новую продукцию не закупаем.",
        ),
        (
            "SERVICES",
            "Сервис ремонта электроники заменяет существующую кредитную задолженность новым обеспеченным кредитом.",
        ),
    ],
    "ip": [
        (
            "SERVICES",
            "Я ИП, реставрирую книги; нужна небольшая сумма на одну закупку обычных расходных материалов.",
        ),
        (
            "TRADE",
            "Индивидуальный предприниматель с магазином аквариумистики разово пополняет оборотные средства, продаж на маркетплейсах нет.",
        ),
    ],
    "no_relevant": [
        ("IT", "Нужен только зарплатный проект для сотрудников. Кредит и заёмные деньги не требуются."),
        ("SERVICES", "Ищем услуги инкассации собственных денег, кредитные предложения не рассматриваем."),
    ],
    "restricted_catalog": [
        (
            "LOGISTICS",
            "Нужна именно возобновляемая линия: возвращённая сумма должна снова становиться доступной. Другой механизм не подходит.",
        ),
        (
            "SERVICES",
            "Обычные текущие расходы фотолаборатории одной суммой; нет ни сезонной потребности, ни продаж на маркетплейсах.",
        ),
    ],
}


def scenario(intent, index, sector, description, variant, split, products):
    purpose = PURPOSE.get(intent, "WORKING_CAPITAL")
    usage = (
        "ACCOUNT_RESERVE"
        if intent == "overdraft"
        else "IN_PARTS"
        if intent in ("revolving", "nonrevolving") or intent == "restricted_catalog" and index % 2 == 0
        else "ONE_TIME"
    )
    secured = intent in ("equipment", "transport", "property", "investment", "refinance")
    collateral = (
        ["YES", "UNKNOWN", "DISCUSS", "YES", "DISCUSS"][variant]
        if secured
        else ["NO", "UNKNOWN", "DISCUSS", "YES", "NO"][variant]
    )
    guarantor = ["YES", "UNKNOWN", "DISCUSS", "YES", "DISCUSS"][variant]
    if intent == "ip" and variant == 4:
        guarantor = "NO"
    text = description
    if variant == 1:
        text = "Описание задачи компании: " + text
    elif variant == 2:
        text += " Сравниваем механизмы финансирования под указанную задачу."
    elif variant == 3:
        text = "План компании на ближайшее время. " + text + " Просим учесть указанное назначение."
    elif variant == 4:
        text += " Важен смысл предложения, а не рекламное название."
    profile = {
        "business": {"sector": None if variant == 1 else sector},
        "request": {
            "purpose": purpose,
            "usageMode": "UNKNOWN" if variant == 2 else usage,
            "description": text,
        },
        "security": {"collateralReady": collateral, "guarantorReady": guarantor},
    }
    codes = (
        [p["code"] for p in products]
        if split == "train"
        else [
            p["code"]
            for p in products
            if purpose in p["purposes"]
            and (variant == 2 or usage in p["usageModes"])
            and (p["code"] != "P13" or intent == "ip")
            and (p["code"] != "P15" or sector == "MANUFACTURING")
        ]
    )
    relevant = list(REL[intent])
    if intent == "equipment" and sector == "MANUFACTURING":
        relevant.append("P15")
    if intent == "investment" and sector == "MANUFACTURING":
        relevant = ["P01", "P10", "P15"]
    if intent == "restricted_catalog":
        codes = ["P04"] if index % 2 == 0 else ["P06", "P14"]
    family = f"ft-v1-{split}-{intent}-{index + 1:02}"
    return {
        "id": family + f"-v{variant + 1}",
        "familyId": family,
        "intent": intent,
        "profile": profile,
        "candidateProductCodes": codes,
        "relevantProductCodes": sorted(set(relevant) & set(codes)),
        "labelStatus": "SYNTHETIC_PROPOSED",
    }


def build():
    products = json.loads((ROOT / "evaluation/backend-products.json").read_text(encoding="utf-8"))["products"]
    train = [
        scenario(intent, i, sector, business + ". " + TASKS[intent][i % 2], v, "train", products)
        for intent in TASKS
        for i, (sector, business) in enumerate(BUSINESSES)
        for v in range(5)
    ]
    final = [
        scenario(intent, i, sector, text, v, "final", products)
        for intent, cases in FINAL_CASES.items()
        for i, (sector, text) in enumerate(cases)
        for v in range(3)
    ]
    old = []
    for name in ("calibration.json", "holdout.json", "reranker-test.json"):
        old += json.loads((ROOT / "evaluation" / name).read_text(encoding="utf-8"))["scenarios"]

    def canonical(s):
        return json.dumps(s["profile"], sort_keys=True, ensure_ascii=False)

    for left, right in ((train, old), (final, old), (train, final)):
        assert not ({canonical(s) for s in left} & {canonical(s) for s in right})
        assert not ({s["familyId"] for s in left} & {s["familyId"] for s in right})
    for name, rows in (("finetune-train.json", train), ("finetune-test.json", final)):
        path = ROOT / "evaluation" / name
        if path.exists():
            raise FileExistsError("Do not overwrite frozen fine-tuning datasets")
        path.write_text(
            json.dumps(
                {
                    "datasetVersion": "e5-finetune-1",
                    "labelStatus": "SYNTHETIC_PROPOSED",
                    "notice": "New train/test families authored before training. Shared fixed product catalog is intentional; this tests new queries, not unseen products.",
                    "scenarios": rows,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    print(
        json.dumps(
            {
                "trainProfiles": len(train),
                "trainFamilies": len({s["familyId"] for s in train}),
                "finalProfiles": len(final),
                "finalFamilies": len({s["familyId"] for s in final}),
            }
        )
    )


if __name__ == "__main__":
    build()
