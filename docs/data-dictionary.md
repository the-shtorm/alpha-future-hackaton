# Данные backend

Текущая схема полей: [Preliminary Form 2.0 / Data Policy 3.0](backend-fields-v3.md).
15 полей формы, 13 переносимых, 17 полей заявки.

Ниже описан сохранённый финансовый алгоритм 2.1 и DEMO-заглушка, а не ML 3.0.

## Финансовые расчеты

- Средняя выручка: revenue / число полных календарных месяцев, Decimal, 8 знаков HALF_UP.
- Стаж: полные месяцы на UTC-день подачи; даты не подменяются текущей датой повторного просмотра.
- Существующая нагрузка: monthlyDebtPayment × periodMonths / revenue.
- Бюджет нового платежа: 0.40 × revenue / periodMonths − monthlyDebtPayment, вниз до копеек.
- Собственное участие: ownContributionPct / 100.
- Аннуитет: A × r × (1+r)^n / ((1+r)^n−1), r=annualRatePct/1200; при нулевой ставке A/n.
  Добавляется явная maintenance_fee_rub из каталога, платеж округляется вверх до копеек.
- Для нестандартных графиков нет выдуманного платежа: REQUEST_INFO/product.paymentSchedule.
- При нулевой выручке — REQUEST_INFO, Infinity/NaN не формируются.
- overdue >0.2: DECLINED, встречное предложение запрещено.
- Неположительный бюджет: DECLINED; снижение суммы не освобождает уже занятый бюджет.

## Временная взвешенная оценка

Только при явном DEMO_ASSESSMENT_ENABLED=true и synthetic=true у продукта:

```text
D = clamp(paymentToRevenue / 0.40, 0, 1)
O = clamp(overdue / 0.20, 0, 1)
A = clamp(amountToMonthlyRevenue / 12, 0, 1)
H = clamp(12 / (operatingAgeMonths + 12), 0, 1)
score = max(0, 1 − 0.45×D − 0.25×O − 0.20×A − 0.10×H)
DEMO threshold = 0.55
riskMarginPct = 15 + 20×(1 − score)
alternative annualRatePct = key_rate_pct + riskMarginPct
```

Это выбранные для воспроизводимого демо веса, а не обученные параметры или банковская
методология. Версия demo-fixed-weights-1; mode=DEMO, isSimulated=true.
При поиске альтернативы оценка и маржа пересчитываются для каждой проверяемой суммы.
Условие: новый платеж + существующие платежи <=40% средней выручки, score>=0.55.
Сумма должна уменьшиться и быть строго больше minAmount. Срок не меняется.
Ставка должна повыситься и не превышать maxAnnualRatePct синтетической политики (100).
Реальные/неподдерживаемые продукты и выключенный DEMO дают REQUEST_INFO, без auto APPROVED.

## Макроконтекст и финансовые операции

Ключевая ставка — отдельная серверная версия: id, keyRatePct, validFrom, expiresAt,
sourceCode, recordedAt. Создание только BANK_APPROVER. В примерах 10 — DEMO fixture,
не актуальная ставка ЦБ. Принятые условия не пересчитываются после смены контекста.

Финансовые операции — отдельный ресурс financial-evidence, не поле анкеты.
Поля операции: externalId, date, amount (денежная строка), direction CREDIT/DEBIT,
category REVENUE/REVENUE_REFUND/INTERNAL_TRANSFER/LOAN/EXPENSE/UNKNOWN.
Суммируются CREDIT/REVENUE и вычитаются DEBIT/REVENUE_REFUND; внутренние переводы,
кредитные поступления и расходы не увеличивают выручку. Повторы externalId запрещены.
UNKNOWN-категория или отсутствие банковской проверки не считаются нулевой выручкой.
После PASS любое точное расхождение с заявленной выручкой направляет на ручную проверку.
Это консервативное правило демо; числовой порог существенности не выдумывается.


Новый сценарий ручного обмена и форма 1.1: [Query/Passage MVP — реализация](ranking-exchange.md).
