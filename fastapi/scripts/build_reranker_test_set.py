"""Author a fresh sealed synthetic test before reranker/criterion results are available."""

import hashlib
import json

from app.core.config import ROOT
from scripts.build_calibration_set import PURPOSE, REL

CASES = {
    "ordinary": [
        (
            "SERVICES",
            "Ветеринарная клиника оплачивает запас медикаментов одной закупкой. Это обычные текущие расходы без сезонности и продаж на маркетплейсах.",
        ),
        (
            "MANUFACTURING",
            "Типографии нужна разовая закупка красок для текущих заказов. Новый станок не нужен, сезонного проекта нет.",
        ),
    ],
    "seasonal": [
        (
            "TRADE",
            "Книжная лавка делает запас учебников перед началом учебного года; основная выручка приходит в августе и сентябре.",
        ),
        (
            "SERVICES",
            "Пляжный прокат финансирует подготовительные текущие расходы к летнему сезону, когда появится основная выручка.",
        ),
    ],
    "marketplace": [
        (
            "MANUFACTURING",
            "Изготавливаем кожаные сумки и продаём их через маркетплейс. Нужен разовый оборотный кредит для товарных запасов на площадке.",
        ),
        (
            "TRADE",
            "Торгуем товарами для домашних животных на Ozon уже два года, пополняем запасы для интернет-площадки одной партией.",
        ),
    ],
    "revolving": [
        (
            "SERVICES",
            "Автомойка закупает химию по мере расходования, погашает долг и снова берёт деньги из восстановленного кредитного лимита.",
        ),
        (
            "AGRICULTURE",
            "Цветочное хозяйство хочет повторно использовать возвращённые суммы для регулярных закупок, нужен возобновляемый лимит.",
        ),
    ],
    "nonrevolving": [
        (
            "IT",
            "В рамках одного проекта закупаем комплектующие по этапам из невозобновляемой линии; погашение не должно восстанавливать доступную сумму.",
        ),
        (
            "TRADE",
            "Оснащаем новый пункт продаж, выбираем оборотный лимит траншами по графику закупок, повторного использования погашенных сумм нет.",
        ),
    ],
    "overdraft": [
        (
            "SERVICES",
            "У стоматологической лаборатории обязательные платежи раньше оплаты от клиник. Нужен овердрафт, который подстрахует расчётный счёт.",
        ),
        (
            "CONSTRUCTION",
            "Заказчик платит за ремонт позже срока выплаты зарплат. Нужен краткосрочный резерв на расчётном счёте, а не инвестиционный кредит.",
        ),
    ],
    "equipment": [
        (
            "MANUFACTURING",
            "Предприятие расширяет производство, приобретая промышленную вышивальную машину. Готовы предоставить обеспечение.",
        ),
        (
            "SERVICES",
            "Фитнес-центр покупает комплект тренажёров одной суммой. Помещение арендуем, покупать его не планируем.",
        ),
    ],
    "transport": [
        (
            "LOGISTICS",
            "Служба экспресс-перевозок покупает коммерческий микроавтобус для доставки, готовы обсуждать залог.",
        ),
        (
            "SERVICES",
            "Кейтеринговая компания приобретает грузовой фургон для развоза заказов. Не просим финансировать кухонное оборудование.",
        ),
    ],
    "property": [
        (
            "TRADE",
            "Ювелирная мастерская выкупает коммерческое помещение для магазина. Нужен кредит на покупку недвижимости.",
        ),
        (
            "SERVICES",
            "Образовательный центр покупает нежилое помещение для занятий, готов обсудить обеспечение покупки.",
        ),
    ],
    "investment": [
        (
            "IT",
            "Компания развивает новую программную платформу и ищет инвестиционное финансирование под залог принадлежащего ей офисного здания.",
        ),
        (
            "MANUFACTURING",
            "Производитель косметики расширяет мощности и инвестирует в дополнительное оборудование и производственную линию.",
        ),
    ],
    "contract": [
        (
            "MANUFACTURING",
            "Швейное предприятие выполняет подписанный контракт на изготовление униформы. Финансирование нужно именно для исполнения контракта.",
        ),
        (
            "IT",
            "Исполняем государственный контракт на техническую поддержку сети учреждений. Нужен кредит на выполнение обязательств по договору.",
        ),
    ],
    "refinance": [
        (
            "TRADE",
            "Сеть магазинов хочет заменить действующий дорогой кредит новым обеспеченным кредитом под залог недвижимости, а не финансировать новую закупку.",
        ),
        (
            "SERVICES",
            "У студии звукозаписи есть кредитные обязательства: требуется рефинансирование с обеспечением коммерческим помещением.",
        ),
    ],
    "ip": [
        (
            "SERVICES",
            "Я индивидуальный предприниматель, ремонтирую велосипеды. Нужен небольшой разовый кредит на текущие расходники.",
        ),
        (
            "TRADE",
            "ИП с обычным газетным киоском разово закупает канцелярские товары. Не работаем на маркетплейсах, сезонной потребности нет.",
        ),
    ],
    "no_relevant": [
        (
            "LOGISTICS",
            "Нужна корпоративная карта только для собственных средств, без кредита и кредитного лимита.",
        ),
        (
            "AGRICULTURE",
            "Ищем консультацию по налоговому учёту. Кредитные деньги не нужны и брать кредит не будем.",
        ),
    ],
    "restricted_catalog": [
        (
            "MANUFACTURING",
            "Цеху нужен восстановляемый лимит: после погашения деньги должны снова быть доступны. Невозобновляемый механизм не подходит.",
        ),
        (
            "SERVICES",
            "Обычные разовые текущие расходы ремонтной мастерской. Сезонности и продаж через маркетплейсы нет.",
        ),
    ],
}


def build():
    source = ROOT / "evaluation/backend-products.json"
    products = json.loads(source.read_text(encoding="utf-8"))["products"]
    rows = []
    for intent, cases in CASES.items():
        for index, (sector, description) in enumerate(cases):
            for variant in range(3):
                purpose = PURPOSE.get(intent, "WORKING_CAPITAL")
                usage = (
                    "ACCOUNT_RESERVE"
                    if intent == "overdraft"
                    else "IN_PARTS"
                    if intent in ("revolving", "nonrevolving")
                    or (intent == "restricted_catalog" and index == 0)
                    else "ONE_TIME"
                )
                secured = intent in ("equipment", "transport", "property", "investment", "refinance")
                collateral = "UNKNOWN" if variant == 1 else "YES" if secured else "NO"
                guarantor = (
                    "UNKNOWN" if variant == 1 else "NO" if intent == "ip" and variant == 2 else "DISCUSS"
                )
                text = (
                    description
                    if variant == 0
                    else "Пояснение компании: " + description
                    if variant == 1
                    else description
                    + " Хотим сравнить варианты для этой задачи, без лишних кредитных предложений."
                )
                if intent == "ordinary" and variant == 2:
                    text = None
                profile = {
                    "business": {"sector": None if variant == 1 else sector},
                    "request": {
                        "purpose": purpose,
                        "usageMode": "UNKNOWN" if variant == 2 else usage,
                        "description": text,
                    },
                    "security": {"collateralReady": collateral, "guarantorReady": guarantor},
                }
                candidates = [
                    p["code"]
                    for p in products
                    if purpose in p["purposes"]
                    and (variant == 2 or usage in p["usageModes"])
                    and (p["code"] != "P13" or intent == "ip")
                    and (p["code"] != "P15" or sector == "MANUFACTURING")
                ]
                relevant = list(REL[intent])
                if intent == "equipment" and sector == "MANUFACTURING":
                    relevant.append("P15")
                if intent == "investment" and sector == "MANUFACTURING":
                    relevant = ["P01", "P10", "P15"]
                if intent == "restricted_catalog":
                    candidates = ["P04"] if index == 0 else ["P06", "P14"]
                rows.append(
                    {
                        "id": f"sealed-v2-{intent}-{index + 1}-v{variant + 1}",
                        "familyId": f"sealed-v2-{intent}-{index + 1}",
                        "intent": intent,
                        "profile": profile,
                        "candidateProductCodes": candidates,
                        "relevantProductCodes": sorted(set(relevant) & set(candidates)),
                        "labelStatus": "SYNTHETIC_PROPOSED",
                    }
                )
    old = []
    for name in ("calibration.json", "holdout.json"):
        old += json.loads((ROOT / "evaluation" / name).read_text(encoding="utf-8"))["scenarios"]

    def canonical(s):
        return json.dumps(s["profile"], sort_keys=True, ensure_ascii=False)

    assert not ({canonical(s) for s in rows} & {canonical(s) for s in old})
    assert not ({s["familyId"] for s in rows} & {s["familyId"] for s in old})
    data = {
        "datasetVersion": "sealed-reranker-test-2",
        "split": "sealed_final_test",
        "productsSha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "labelStatus": "SYNTHETIC_PROPOSED",
        "notice": "Authored before reranker scores. Old holdout is development now. Only evaluate this test after freezing primary model/criterion on development.",
        "scenarios": rows,
    }
    path = ROOT / "evaluation/reranker-test.json"
    if path.exists():
        raise FileExistsError("Do not overwrite an existing sealed test")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "scenarios": len(rows),
                "families": len({s["familyId"] for s in rows}),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    )


if __name__ == "__main__":
    build()
