> Исходный материал проектирования. [Контекст и действующая документация](README.md).

# Словарь данных и Политика разметки для ML-скоринга (Data Policy)

Версия 3.0 (Гармонизирована с датасетом SBA 7(a), `preliminary_form.md` и `query_passage_mvp.md`). Документ описывает единый контракт данных бэкенда (Spring Boot) и сервиса моделей (FastAPI) для финальной кредитной заявки, двухуровневого гибридного скоринга и расчета встречных предложений.

## 1. Общие правила представления и нормализации

Данные кредитной анкеты используются как в бизнес-правилах Spring Boot, так и в ML-модели скоринга (обученной на датасете SBA 7(a)). Для исключения ошибок масштаба закрепляются следующие правила типов:

| Тип в API / форме | Формат хранения и передачи (JSON) | Правило нормализации для расчетов и ML | Пример |
| --- | --- | --- | --- |
| `money` | Десятичная строка в `RUB`, 2 знака после точки | В бизнес-правилах используется в `RUB`. Для ML-модели SBA конвертируется в `USD` делением на расчетный курс `FX_RATE` | `"1800000.00"` (`RUB`) $\to$ `"20000.00"` (`USD`) |
| `rate_pct` | Десятичная строка (процентные пункты) | **Не делится на 100** при подаче в ML-модель SBA (в датасете SBA `6.0` означает $6\%$). В формулах аннуитета делится на $1200$ | `"28.00"` $\to$ `28.0` (в ML) / $0.28$ (в формуле) |
| `share` / `overdue` | Число с плавающей точкой (`float`) в $[0, 1]$ | Уже нормализовано как доля от $0$ до $1$ | `0.15` ($15\%$) |
| `percent` | Десятичная строка от `"0.00"` до `"100.00"` | Переводится в долю $[0, 1]$ делением на $100$ для внутренних проверок | `"20.00"` $\to$ `0.20` |
| `date` | Строка `YYYY-MM-DD` (UTC) | Конвертируется в полные месяцы стажа, а для модели SBA — в строковую категорию `BusinessAge` | `"2020-01-01"` $\to$ `81` мес. $\to$ `"Existing, 5 or more years"` |
| `boolean` | JSON `true` / `false` | В модели SBA соответствует флагам `Y` (`1`) / `N` (`0`) | `true` $\to$ `1` |
| `enum` | Строковый код в верхнем регистре | Маппится по строгому словарю в категории модели (One-Hot / Target Encoding) | `LLC` $\to$ `CORPORATION` |

**Качество данных и обработка пропусков (`value_status`):**
* `KNOWN`: Значение известно и прошло валидацию (включая подтвержденный математический ноль: `"0.00"` или `0`).
* `UNKNOWN`: Поле не заполнено (`null`) или выбран ответ `UNKNOWN`. В обязательных полях финальной заявки блокирует скоринг и переводит заявку в `REQUEST_INFO`.
* `INVALID`: Нарушен формат или логический диапазон (например, `periodFrom > periodTo` или отрицательная выручка). Вызывает ошибку `400 INVALID_INPUT`.

## 2. Жизненный цикл заявки и роли

В системе взаимодействуют клиентский контур (`OWNER`, `EDITOR`, `VIEWER`) и контур сотрудника банка (`BANK_APPROVER`).

**Маршрут обработки заявки:**
```text
DRAFT -> SUBMITTED -> VALIDATING -> ENRICHING -> SCORING (FastAPI ML + Policy) -> UNDER_REVIEW
      -> APPROVED / COUNTEROFFERED -> OFFER_ACCEPTED -> SIGNED -> READY_FOR_DISBURSEMENT -> DISBURSED
```

* **Возврат на доработку (`REQUEST_INFO` / статус `NEEDS_INFO`):** Происходит автоматически, если при подаче не заполнены обязательные финансовые поля (`monthlyDebtPayment`, `overdue`) или период выручки не образует полных календарных месяцев.
* **Встречное предложение (`COUNTEROFFERED`):** Формируется, если по запрошенным параметрам вероятность дефолта из ML-модели или долговая нагрузка (PTI) превышают порог одобрения, но снижение суммы или корректировка ставки позволяют уложиться в риск-аппетит банка.

## 3. Поля окончательной заявки (Входные данные `answers`)

В окончательной заявке используются **16 полей**: 12 наследуются из предварительной формы (`preliminary_form.md`), а 4 дозаполняются клиентом перед нажатием «Отправить заявку».

### 3.1. Поля, наследуемые из предварительной формы (12 полей)

На этапе подачи заявки значения `UNKNOWN` в полях `business.sector` и `business.taxRegime` больше не допускаются — клиент обязан их уточнить.

* `request.amount` (`money`, `RUB`): Запрошенная сумма кредита.
* `request.termMonths` (`integer`): Запрошенный срок в месяцах.
* `request.purpose` (`enum`): Цель финансирования.
* `registration.borrowerKind` (`enum`: `IP`, `LLC`): Форма бизнеса.
* `business.sector` (`enum`): Отрасль бизнеса (`TRADE`, `MANUFACTURING`, `SERVICES`, `IT`, `CONSTRUCTION`, `AGRICULTURE`, `LOGISTICS`).
* `business.actualStartedOn` (`date`): Дата фактического начала деятельности.
* `business.taxRegime` (`enum`: `OSNO`, `USN`, `PSN`, `AUSN`, `NPD`): Действующий налоговый режим.
* `business.mspRegistry` (`boolean`): Статус участника реестра МСП.
* `financial.revenue` (`money`, `RUB`): Выручка за период.
* `financial.periodFrom` / `financial.periodTo` (`date`): Границы периода выручки.
* `security.collateralReady` (`enum`: `YES`, `NO`, `DISCUSS`): Подтвержденная готовность предоставить залог.
* `security.guarantorReady` (`enum`: `YES`, `NO`, `DISCUSS`): Подтвержденная готовность предоставить поручителя.

### 3.2. Поля, дозаполняемые при подаче заявки (4 поля)

* `financial.monthlyDebtPayment` (`money`, `RUB`): Сумма текущих ежемесячных платежей по действующим бизнес-долгам (`"0.00"`, если долгов нет). Обязательно для этапа `SCORING`.
* `financial.overdue` (`float` в диапазоне $[0, 1]$): Доля просроченных платежей в истории компании (`0` — ни один платеж не просрочен, `1` — все платежи просрочены). Обязательно для этапа `SCORING`.
* `security.collateralValue` (`money`, `RUB`): Оценочная стоимость предлагаемого залога (`"0.00"`, если залог не предоставляется). Обязательно, если по продукту залог `REQUIRED` или клиент ответил `YES`.
* `project.ownContributionPct` (`percent`, `"0.00"`..`"100.00"`): Доля собственных средств в финансируемом проекте. Условно обязательно, если в политике продукта `min_own_contribution_pct > 0`.

### 3.3. Технические поля выбранного продукта (из каталога БД)

Для работы ML-модели и формул платежа из карточки выбранной версии продукта (`ProductVersion`) автоматически подтягиваются:
* `product.annualRatePct` (`rate_pct`): Базовая годовая процентная ставка продукта (например, `"28.00"`).
* `product.interestRateType` (`enum`: `FIXED`, `VARIABLE`): Тип процентной ставки (в демо-каталоге по умолчанию `FIXED`).
* `product.type` (`enum`: `TERM_LOAN`, `REVOLVING_CREDIT_LINE`, `NON_REVOLVING_CREDIT_LINE`, `OVERDRAFT`): Механизм финансирования.
* `product.minAmount`, `product.maxAmount`, `product.minTermMonths`, `product.maxTermMonths`: Допустимые границы продукта для расчета встречного предложения.

## 4. Двухуровневый гибридный скоринг (FastAPI + Spring Boot)

Поскольку реальный датасет SBA 7(a) (`dataset_new.md`) не содержит показателей выручки, текущих платежей и доли просрочек, но содержит историческую статистику списаний по параметрам сделок и профилю компаний, этап `SCORING` разделен на два последовательных шага.

### 4.1. Шаг 1: Контракт вызова ML-модели SBA 7(a) в FastAPI

Spring Boot формирует нормализованный JSON-запрос из 9 признаков, строго соответствующих обученной модели SBA 7(a):

| Поле в JSON-запросе FastAPI | Поле в датасете SBA | Тип данных | Правило вычисления из заявки и продукта |
| --- | --- | --- | --- |
| `loanAmountUsd` | `GrossApproval` | `decimal` string | $\text{round}(\text{request.amount} / \text{FX\_RATE}, 2)$, где `FX_RATE = 90.00` (фиксированный курс для сопоставимости масштаба с SBA) |
| `termMonths` | `TermInMonths` | `integer` | Напрямую из `request.termMonths` ($\ge 1$) |
| `initialInterestRatePct` | `InitialInterestRate` | `decimal` string | Из `product.annualRatePct` в процентных пунктах (например, `"28.00"`) |
| `interestRateType` | `FixedorVariableInterestInd` | `enum` | Из `product.interestRateType`: `FIXED` (в CSV `F`) или `VARIABLE` (в CSV `V`) |
| `isRevolving` | `RevolverStatus` | `boolean` | `true` (в CSV `Y`), если `product.type` $\in \{\text{REVOLVING\_CREDIT\_LINE}, \text{OVERDRAFT}\}$, иначе `false` (`N`) |
| `hasCollateral` | `CollateralInd` | `boolean` | `true` (в CSV `Y`), если `security.collateralValue > 0` и `security.collateralReady == YES`, иначе `false` (`N`) |
| `businessType` | `BusinessType` | `enum` | Если `registration.borrowerKind == LLC` $\to$ `CORPORATION`; если `IP` $\to$ `INDIVIDUAL` |
| `businessAgeCategory` | `BusinessAge` | `string` (enum) | По числу полных месяцев стажа $m = \text{full\_months}(\text{actualStartedOn}, \text{as\_of})$:<br>• $m < 12 \to$ `"New, Less than 1 Year old"`<br>• $12 \le m < 24 \to$ `"New Business or 2 years or less"`<br>• $24 \le m < 36 \to$ `"Less than 3 years old but at least 2"`<br>• $36 \le m < 48 \to$ `"Less than 4 years old but at least 3"`<br>• $48 \le m < 60 \to$ `"Less than 5 years old but at least 4"`<br>• $m \ge 60 \to$ `"Existing, 5 or more years"` |
| `naicsCode` | `NaicsCode` | `string` (6 цифр) | Детерминированный маппинг из `business.sector` (см. таблицу в `dataset_new.md`, раздел 4) |

**Ответ ML-сервиса FastAPI:**
Возвращает базовую вероятность дефолта (списания `CHGOFF`) $p_{\text{sba}} \in [0, 1]$ и технический скоринговый балл $\text{score} = \text{round}(100 \times (1 - p_{\text{sba}}))$.

### 4.2. Шаг 2: Финансовые коэффициенты, просрочки и ключевая ставка ЦБ

На втором шаге к результату ML-модели применяются финансовые данные из раздела 3.2 и системный макро-параметр:
* `macroeconomic.key_rate_pct` (`rate_pct`): Текущая ключевая ставка ЦБ РФ (например, `"21.00"`).

**Расчетные показатели второго шага:**
1. **Среднемесячная выручка (`averageMonthlyRevenue`):**
   $$\text{averageMonthlyRevenue} = \frac{\text{financial.revenue}}{\text{period\_months}}$$
2. **Ожидаемый ежемесячный платеж по новому кредиту (`estimatedMonthlyPayment`):**
   Для ставки $r = \text{annualRatePct} / 1200$ и срока $n = \text{termMonths}$:
   $$\text{estimatedMonthlyPayment} = \frac{\text{amount}}{n} + \text{amount} \times r$$
3. **Коэффициент долговой нагрузки с учетом нового кредита (`debt.payment_to_revenue_with_request`):**
   $$\text{PTI} = \frac{\text{financial.monthlyDebtPayment} + \text{estimatedMonthlyPayment}}{\text{averageMonthlyRevenue}}$$
4. **Скорректированная вероятность риска с учетом просрочек ($p_{\text{final}}$):**
   * Если $\text{financial.overdue} > 0.20$: срабатывает жесткий стоп-фактор $\to$ решение `DECLINED` без расчета встречных предложений.
   * Если $0 \le \text{financial.overdue} \le 0.20$: линейная надбавка к риску модели SBA:
     $$p_{\text{final}} = \min\left(1.0,\; p_{\text{sba}} + 0.50 \times \text{financial.overdue}\right)$$

### 4.3. Алгоритм принятия решения и генерации `COUNTEROFFERED`

1. **Условие прямого одобрения (`APPROVED`):**
   Если $p_{\text{final}} \le 0.15$ (порог низкого риска) **И** $\text{PTI} \le 0.40$ (платежи не превышают $40\%$ среднемесячной выручки) $\to$ заявка получает статус `APPROVED` на запрошенных клиентом условиях (`request.amount`, `request.termMonths`, `product.annualRatePct`).
2. **Условие формирования встречного предложения (`COUNTEROFFERED`):**
   Если $0.15 < p_{\text{final}} \le 0.35$ (умеренный риск) **ИЛИ** $\text{PTI} > 0.40$ при базовых условиях:
   * **Пересчет ставки в пользу банка:** Рассчитывается индивидуальная ставка на базе ключевой ставки ЦБ и премии за риск:
     $$\text{altRatePct} = \max\left(\text{product.annualRatePct},\; \text{key\_rate\_pct} + 5.0 + 20.0 \times p_{\text{final}}\right)$$
   * **Оптимизация срока и суммы:** Если $\text{PTI} > 0.40$, срок увеличивается до $\text{altTermMonths} = \min(\text{request.termMonths} + 12, \text{product.maxTermMonths})$. Далее вычисляется максимальная сумма кредита $\text{altAmount}$, при которой суммарный платеж равен ровно $40\%$ среднемесячной выручки:
     $$\text{maxNewPayment} = 0.40 \times \text{averageMonthlyRevenue} - \text{financial.monthlyDebtPayment}$$
     $$\text{altAmount} = \min\left(\text{request.amount},\; \frac{\text{maxNewPayment}}{\frac{1}{\text{altTermMonths}} + \frac{\text{altRatePct}}{1200}}\right)$$
   * **Проверка границ:** Если $\text{altAmount} \ge \text{product.minAmount}$, система повторно оценивает сделку в модели SBA с новой суммой и ставкой и выдает вердикт `COUNTEROFFERED`. Если даже минимальная сумма продукта превышает $40\%$ нагрузки или $p_{\text{final}} > 0.35$ $\to$ выдается `DECLINED`.

## 5. Структура объекта решения (Decision & Offer)

Результат работы гибридного алгоритма сохраняется в объекте `Decision`:

| Поле | Тип | Описание |
| --- | --- | --- |
| `kind` | `enum` | `APPROVED`, `COUNTEROFFERED`, `DECLINED`, `REQUEST_INFO` |
| `reason` | `string` | Понятное объяснение результата для клиента и кредитного инспектора |
| `conditions` | `object` | Аудит расчета: `sbaDefaultProbability` ($p_{\text{sba}}$), `finalRiskScore` ($p_{\text{final}}$), `keyRatePct`, `averageMonthlyRevenue`, `estimatedFirstMonthPayment`, `totalMonthlyPayment`, `debtServiceToRevenueRatio` ($\text{PTI}$), `missingFields` |
| `alternative_terms` | `object` \| `null` | Заполняется при `COUNTEROFFERED`: `{ "amount": money, "termMonths": integer, "annualRatePct": rate_pct }` |

При `APPROVED` в объект `Offer.terms` переносятся исходные условия запроса; при `COUNTEROFFERED` в `Offer.terms` записываются параметры из `alternative_terms`. После вызова клиентом `accept` $\to$ `sign` $\to$ `disburse` сделка завершается моделируемой выдачей средств.