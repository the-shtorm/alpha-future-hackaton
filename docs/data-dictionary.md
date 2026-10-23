# Данные backend: две отдельные схемы

Источники: [Preliminary Form 1.0](preliminary_form.md), [Data Policy 2.1](data-policy.md).

## Предварительная форма: 19 полей

| Поле | Тип JSON | Назначение |
|---|---|---|
| `registration.borrowerKind` | enum string | IP / LLC |
| `business.sector` | enum string | Отрасль |
| `business.mspRegistry` | boolean | Членство в МСП; не категория размера |
| `registration.registeredOn` | date string | YYYY-MM-DD |
| `business.actualStartedOn` | date string | Не раньше регистрации |
| `business.taxRegime` | enum string | OSNO/USN/PSN/AUSN/NPD/COMBINED/OTHER/UNKNOWN |
| `financial.revenue` | decimal string | Выручка за период |
| `financial.periodFrom` | date string | Начало периода |
| `financial.periodTo` | date string | Конец периода |
| `request.purpose` | enum string | Цель из каталога |
| `request.amount` | decimal string | Желаемая сумма |
| `request.termMonths` | integer | Срок в месяцах |
| `registration.country` | enum string | Условное: страна |
| `business.region` | string | Условное: регион |
| `business.ipAgeYears` | integer | Условное: только IP |
| `security.collateralReady` | boolean | Условное: готовность к залогу |
| `security.guarantorReady` | boolean | Условное: готовность к поручителю |
| `business.marketplaceMonths` | integer | Условное: стаж маркетплейса |
| `business.bankAccountMonths` | integer | Условное: стаж счета |

Первые 12 — основной набор, последние 7 — условные поля продуктов/сценариев.
Долги, доля просрочек, стоимость залога и собственное участие сюда не принимаются.
Частичное сохранение разрешено. Проверка применимости не принимает кредитных решений.

## Окончательная заявка: 15 полей

| Поле | Тип JSON | Назначение |
|---|---|---|
| `registration.borrowerKind` | enum string | IP / LLC |
| `business.mspRegistry` | boolean | Членство в МСП; не категория размера |
| `registration.registeredOn` | date string | YYYY-MM-DD |
| `business.actualStartedOn` | date string | Не раньше регистрации |
| `business.taxRegime` | enum string | OSNO/USN/PSN/AUSN/NPD/COMBINED/OTHER/UNKNOWN |
| `financial.revenue` | decimal string | Выручка за период |
| `financial.periodFrom` | date string | Начало периода |
| `financial.periodTo` | date string | Конец периода |
| `request.purpose` | enum string | Цель из каталога |
| `request.amount` | decimal string | Желаемая сумма |
| `request.termMonths` | integer | Срок в месяцах |
| `financial.monthlyDebtPayment` | decimal string | Новый ввод: текущие платежи, 0 если нет |
| `financial.overdue` | decimal number | Новый ввод: доля [0,1], не boolean и не строка |
| `security.collateralValue` | decimal string | Новый ввод: стоимость обеспечения |
| `project.ownContributionPct` | decimal percent string | Новый ввод: процент собственных средств 0..100 |

Переносятся только 11 общих полей. Четыре новых поля заполняются отдельно.
Остальные восемь полей подбора остаются в preliminaryContext, не в answers заявки.
Для банковской проверки требуются 11 общих полей и платежи/просрочка; стоимость
обеспечения и собственное участие обязательны по условиям продукта.
Для создания черновика нужны сумма/срок/цель/форма бизнеса; остальное можно дополнить.
ИНН, название компании, владельцы и выбранная версия продукта — отдельные серверные реквизиты.

## Типы, пропуски и подтверждение

Деньги — неотрицательная десятичная строка до 17 цифр целой части и 2 после точки;
сумма кредита положительна. Процент собственных средств — строка 0..100.
Срок — integer 1..1200; прочий стаж — integer 0..1200. Даты — прошедшие YYYY-MM-DD.
Строки непустые, до 1000 символов. Будущие даты и несовместимый режим ООО отклоняются.

value_status: KNOWN для известного допустимого значения (включая 0/false), UNKNOWN для
пропуска/null/кода UNKNOWN, INVALID для технически невозможного значения.
Невалидный ввод API отклоняет 400. Источник и verification_status учитываются отдельно:
ручные сведения сохраняются DECLARED, а подтверждение владельцем фиксируется при submit.
KNOWN не означает независимую проверку банком или реестром.

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
