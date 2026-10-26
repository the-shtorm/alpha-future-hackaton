# Контракт полей backend: Preliminary Form 2.0 / Data Policy 3.0

Источники: [предварительная форма 2.0](reference/preliminary-form-2.0.md),
[Data Policy 3.0](reference/data-policy-3.0.md),
[Query/Passage MVP](reference/query-passage-mvp-source.md).
Анализ датасета SBA и прежний dataset_fields_review.md не являются основанием этой схемы.

В источниках опечатка в количествах: перечислены **15 отдельных полей формы**, **13
переносимых полей** и **17 полей заявки**, а не 14/12/16. Использованы перечисленные
имена; financial.periodFrom и financial.periodTo считаются отдельно. Поля версии
`preliminary-2.0` и `application-3.0` доступны через GET /forms/preliminary и
GET /forms/application. Финансовая обработка описана в [кредитном скоринге](credit-scoring.md).

## Предварительная форма

| Поле | Тип JSON | Значения / смысл | Перенос в заявку |
|---|---|---|---|
| `registration.borrowerKind` | enum string | IP / LLC | Да |
| `business.sector` | enum string / null | TRADE / MANUFACTURING / SERVICES / IT / CONSTRUCTION / AGRICULTURE / LOGISTICS | Да |
| `business.actualStartedOn` | date string | Фактическое начало деятельности; YYYY-MM-DD | Да |
| `business.taxRegime` | enum string | OSNO / USN / PSN / AUSN / NPD / UNKNOWN | Да |
| `business.mspRegistry` | boolean / null | true / false; null означает отсутствие сведений | Да |
| `financial.revenue` | money string | Общая выручка в RUB за период | Да |
| `financial.periodFrom` | date string | Начало периода; для расчёта нужно 1-е число месяца | Да |
| `financial.periodTo` | date string | Конец периода; для расчёта нужен последний день месяца | Да |
| `request.purpose` | enum string | WORKING_CAPITAL / CASH_GAP / EQUIPMENT / TRANSPORT / COMMERCIAL_PROPERTY / CONTRACT_EXECUTION / REFINANCING / DEVELOPMENT | Да |
| `request.amount` | money string | Сумма/лимит > 0, RUB | Да |
| `request.termMonths` | integer | От 1 до 360 включительно | Да |
| `request.usageMode` | enum string | ONE_TIME / IN_PARTS / ACCOUNT_RESERVE / UNKNOWN | Нет |
| `request.description` | string / null | Необязательный текст до 500 символов без HTML | Нет |
| `security.collateralReady` | enum string / null | YES / NO / DISCUSS / UNKNOWN | Да |
| `security.guarantorReady` | enum string / null | YES / NO / DISCUSS / UNKNOWN | Да |

Сохранение частичного черновика разрешено. Перед eligibility нужны borrowerKind,
purpose, amount, termMonths, usageMode. UNKNOWN допустим для usageMode и пропускает
проверку совместимости. Неизвестную отрасль предпочтительно передавать null;
UNKNOWN также принимается как явно неизвестное значение черновика, никогда не как
подтверждённая отрасль. Для ООО PSN и NPD недопустимы.

Если `financial.revenue` известна, включая `"0.00"`, перед eligibility обязательны
обе даты периода: начало — первое число месяца, конец — последний день месяца.
Неполный период можно сохранить в черновике, но запрос подбора вернёт 400 INVALID_INPUT
с указанием поля. Низкая известная среднемесячная выручка исключает продукты по их
минимальным требованиям; неизвестная выручка не заменяется нулём.
Текущие проверки — `eligibility-3.1`. История старых запусков сохраняется, но для выбора,
обмена ранжированием и переноса в заявку нужен повторный подбор по текущим правилам;
использование старого запуска возвращает 409 SELECTION_STALE.

## Дополнительные поля заявки

| Поле | Тип JSON | Обязательность перед расчётом |
|---|---|---|
| `financial.monthlyDebtPayment` | money string | Всегда; `"0.00"`, если долгов нет |
| `financial.overdue` | number, [0,1] | Всегда; 0 — подтверждённое отсутствие просрочек |
| `security.collateralValue` | money string | Если залог обязателен по продукту либо collateralReady=YES; нужна положительная стоимость |
| `project.ownContributionPct` | percent string, 0.00..100.00 | Если у продукта min_own_contribution_pct > 0 |

В answers заявки переходят все 13 общих полей, включая отрасль и обе готовности.
Только usageMode и description остаются в preliminaryContext. Их нельзя дописать
в answers полной заявки. Неизвестные sector, taxRegime, готовности и прочие обязательные
поля блокируют расчёт: REQUEST_INFO (NEEDS_INFO). DISCUSS — известная готовность
обсудить условие, но не подтверждённый залог или поручитель. Невалидный формат — 400
INVALID_INPUT. KNOWN не означает проверку банком; ручные ответы сохраняются DECLARED.

## Форматы и проверки

- Money и percent: неотрицательные **строки ровно с двумя знаками** после точки,
  до 17 цифр целой части; `"0.00"` допустим, число 0 и строка `"0"` не соответствуют формату.
- Доля overdue: JSON number, не строка/boolean; 0 и 1 допустимы.
- Даты: YYYY-MM-DD, не позже текущего UTC-дня; periodFrom <= periodTo.
  Неполные календарные месяцы сохраняются в черновике, но требуют уточнения перед расчётом.
- Стаж бизнеса считается только по business.actualStartedOn. Дата регистрации
  организации остаётся реквизитом компании, а не полем формы или заявки.
- Отсутствие/null/UNKNOWN не подменяются нулём или false.
- Удалены registration.registeredOn, registration.country, business.region,
  business.ipAgeYears, business.marketplaceMonths, business.bankAccountMonths.
  Они отклоняются при новом вводе; информация о компании в /companies не удаляется.
- Технические product.type, product.interestRateType, product.annualRatePct,
  minAmount/maxAmount/minTermMonths/maxTermMonths приходят из каталога, не из answers.
  Ставка — строка в процентных пунктах, без деления на 100; type использует
  TERM_LOAN / REVOLVING_CREDIT_LINE / NON_REVOLVING_CREDIT_LINE / OVERDRAFT.
  Каталог дополнительно отдаёт usageModes из механизма финансирования.

## Применимость и Recsys

Spring проверяет сумму, срок, цель, форму бизнеса, отрасль, стаж, выручку, налоги,
МСП, режим использования и требования обеспечения. Несовместимый известный режим
использования исключает продукт; UNKNOWN пропускает эту проверку. Обязательный
залог/поручитель + NO исключает; DISCUSS/UNKNOWN/null сохраняют предупреждение.
Условия стажа счёта/маркетплейса остаются отдельными предупреждениями REVIEW по
продукту, без требования снова заполнить удалённые поля. Из короткой формы нельзя
сделать вывод о прохождении этих условий; при рассмотрении требуется проверка.
Географию и возраст физлица эта версия формы не проверяет.

В queryFields входят только шесть полей: sector, purpose, usageMode, description,
collateralReady, guarantorReady. Денежные поля и сведения будущей заявки в этот
семантический блок не попадают. schemaVersion обмена = query-passage-mvp-2.
Recsys возвращает всех кандидатов, rank, similarityScore [-1,1], isRecommended и
неизменённые eligibilityStatus/pendingConditions. Это не вероятность одобрения.
Эмбеддинги и ранжирование выполняет рабочая E5; [контракт обмена](ranking-exchange.md).

## Совместимость и хранение

Не меняются старые миграции, ревизии, решения и снимки подбора. Массового удаления
данных и автоматической миграции ответов нет. Старый профиль при новом eligibility,
выборе или переносе возвращает 409 FORM_UPGRADE_REQUIRED. PATCH с актуальной
expectedVersion и answers={} сохраняет проекцию новой схемы, повышает rowVersion и
сбрасывает выбор; новые/исправленные поля можно передать тем же PATCH. Затем нужен
новый eligibility и выбор. Переданные в PATCH удалённые поля возвращают 400.

PATCH редактируемой старой заявки сохраняет только текущую схему и дополняет
отрасль/готовности из её исходного preliminaryContext, если ответы ещё отсутствуют.
Наследование выполняется только при обновлении старой версии схемы; при следующих
сохранениях очищенные значения из контекста не восстанавливаются. Окончательные
ответы имеют приоритет, patch — последний. Нулевые/неизвестные значения
не додумываются; отсутствующее нужно уточнить. Перенос нового контекста сам по себе
не перезаписывает answers. Старые поданные снимки остаются неизменными.

Две новые версии синтетических продуктов P10/P15 заменяют цель INVESTMENT на
DEVELOPMENT; исходные версии остаются в БД. Каталог показывает по одной последней
активной версии продукта. Добавлен отдельный repeatable SQL после исходного seed.
Существующие заявки продолжают ссылаться на выбранную историческую версию.

## Финансовая обработка

Новые ревизии используют `data-policy-3.0-sba-annuity-1`: аннуитет, платёжный
бюджет, SBA CatBoost, FX/NAICS-маппинг и встречные условия. Полный алгоритм
приведён в [credit-scoring.md](credit-scoring.md). Форма, выбор продукта,
документы, банковское рассмотрение, акцепт и учебная выдача доступны в UI.

## Примеры и Postman

[15 полей preliminary answers](contracts/preliminary-2.0.example.json),
[4 дополнения к заявке](contracts/application-3.0-additions.example.json).
Передайте первый объект в answers запроса POST /selection-profiles; получите runId
через eligibility, выберите подходящий продукт, создайте /applications с profileId,
expectedProfileVersion и вторым объектом в answers. Проверьте в ответе перенос
business.sector и обоих security.*Ready, отсутствие usageMode/description в answers.

Проверки: termMonths=360 принимается, 361/0/12.0 отклоняются; amount="1000.00"
принимается, 1000/"1000"/"-1.00" отклоняются; IT/LOGISTICS принимаются, старый
sector=TRANSPORT отклоняется; taxRegime=PSN для LLC отклоняется. Попытки передать
удалённые поля дают 400, в eligibility без пяти обязательных ответов — 400.
Для UNKNOWN sector/taxRegime/готовностей в заявке validate/банковское рассмотрение
возвращает REQUEST_INFO, а не выдуманную оценку.
