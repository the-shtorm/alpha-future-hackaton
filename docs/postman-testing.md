> Актуальная схема: [Preliminary Form 2.0 / Data Policy 3.0](backend-fields-v3.md). Изменены поля; алгоритм ML 3.0 не реализован.

# Postman: Data Policy 2.1 / Preliminary Form 2.0

Это новая последовательность: форма подбора → eligibility → выбор → отдельная заявка.
Старые запросы создания заявки через partyId/productVersionId заменены созданием из profileId.
[Endpoints](backend-api.md), [точные типы](data-dictionary.md), [автоматические проверки](validation.md).

## Подготовка

В .env: SPRING_PROFILES_ACTIVE=demo, DEMO_PASSWORD, DEMO_BANK_PASSWORD,
DEMO_ASSESSMENT_ENABLED=true. Пароли минимум 12 символов, максимум 72 байта UTF-8.
Запуск: `docker compose up --build -d`. Учитывайте BACKEND_PORT.
В Postman environment: baseUrl=http://localhost:8080, ownerToken, bankToken,
partyId, profileId, runId, productVersionId, applicationId, expectedVersion,
revisionId, proposalId, termsSha256, offerId, documentVersionId, evidenceId.
Пароли и токены храните как локальные Secret-переменные.

JSON-запросы: Body/raw/JSON. Успешные команды возвращают 200.
Authorization/Bearer Token: ownerToken для клиента, bankToken для банка.
Проверка по умолчанию:

```javascript
pm.test("HTTP 200", () => pm.response.to.have.status(200));
```

## 1. Вход и макроконтекст

POST /auth/login, No Auth, тело `{ "login":"demo-owner", "password":"ваш пароль" }`.
Сохраните accessToken в ownerToken. Повторите для demo-bank → bankToken.
GET /me с ownerToken: выберите компанию, сохраните parties[].id в partyId.
GET /demo/scenarios: доступны восемь синтетических компаний и подготовленные формы.
Для их использования берите partyId именно выбранного сценария.

Банк: POST /bank/macroeconomic-contexts:

```json
{"keyRatePct":"10.00000","validFrom":"2026-10-01T00:00:00Z","expiresAt":"2026-11-01T00:00:00Z","sourceCode":"DEMO_FIXTURE_NOT_CBR"}
```

Задайте действующий период на момент проверки. **10 — только искусственный тестовый пример,
не текущая ставка ЦБ.** GET /bank/macroeconomic-contexts/current возвращает ту же версию.
С ownerToken создание должно дать 403. Просроченный/будущий контекст —400.

## 2. Создать предварительную форму

POST /selection-profiles с ownerToken:

```json
{
 "partyId":"{{partyId}}",
 "answers":{
  "request":{"purpose":"WORKING_CAPITAL","usageMode":"ONE_TIME","amount":"1000000.00","termMonths":12},
  "registration":{"borrowerKind":"LLC"},
  "business":{"actualStartedOn":"2020-01-01","sector":"TRADE","taxRegime":"USN","mspRegistry":true},
  "financial":{"revenue":"24000000.00","periodFrom":"2025-10-01","periodTo":"2026-09-30"},
  "security":{"collateralReady":"NO","guarantorReady":"YES"}
 }
}
```

Для текущей даты учитывайте прошедший полный финансовый период. Для IP используется
соответствующая компания кабинета; возраст физлица в форму не передается.
Сохраните id в profileId, rowVersion (первоначально 0). Денег/просрочек окончательной заявки
в этой форме нет. Добавление overdue или monthlyDebtPayment должно вернуть 400.
Частичная форма с answers={} допустима: незаполненные поля UNKNOWN.

## 3. Подбор и выбор

POST /selection-profiles/{{profileId}}/eligibility без тела. Сохраните runId.
Ответ: items со status, reasons (code/field/result/message/actual/expected).
personalRatingAvailable=false; порядок ELIGIBILITY_THEN_PRODUCT_CODE, не вероятность одобрения.
Выберите P01, сохраните его productVersionId.

PUT /selection-profiles/{{profileId}}/selected-product:

```json
{"expectedVersion":0,"runId":"{{runId}}","productVersionId":"{{productVersionId}}"}
```

Ответ содержит выбранный продукт и rowVersion=1. Сохраните текущую версию.
GET /selection-profiles/{{profileId}}/recommendations/{{runId}} возвращает сохраненный результат.
Для проверки устаревания используйте другой профиль: PATCH с актуальной версией
меняет сумму/поле, сбрасывает выбор; прежний run нельзя выбрать (409).
Для суммы выше всех лимитов items будут INELIGIBLE; это не кредитный DECLINED.

## 4. Создать отдельную заявку

POST /applications:

```json
{
 "profileId":"{{profileId}}","expectedProfileVersion":1,
 "answers":{
  "financial":{"monthlyDebtPayment":"0.00","overdue":0},
  "security":{"collateralValue":"0.00"},
  "project":{"ownContributionPct":"0.00"}
 }
}
```

Сохраните id в applicationId, rowVersion в expectedVersion.
Проверьте: 13 общих полей перенесены, включая sector/collateralReady/guarantorReady; usageMode
и description остались только в preliminaryContext. verification_status ручных значений —DECLARED.
Попытка добавить в answers заявки usageMode, description или taxId →400.
GET /applications и /applications/{{applicationId}} — чтение состояния.
POST /applications/{{applicationId}}/validate — предварительный расчет, не сохраненное решение банка.

## 5. Документы продукта

GET /applications/{{applicationId}}/requirements. Для P01/LLC нужен GUARANTEE_CONTRACT.
Для каждого требования загрузите файл: POST /applications/{{applicationId}}/documents,
Body/form-data: typeCode Text=код требования, file File=PDF/PNG/JPEG до 10 MB.
Не задавайте multipart Content-Type вручную: boundary ставит Postman.
Сохраните versionId. Первоначальный value_status=UNKNOWN.
GET /documents/{{documentVersionId}} с токеном возвращает исходные байты.

Банк: POST /bank/applications/{{applicationId}}/documents/{{documentVersionId}}/review:

```json
{"result":"PASS","reason":"Ручная проверка демонстрационного документа"}
```

С ownerToken →403. Без PASS обработка даст REQUEST_INFO с documents.*.
После каждой загрузки перечитайте rowVersion заявки.

## 6. Подать и обработать

GET /applications/{{applicationId}}: обновите expectedVersion.
POST /applications/{{applicationId}}/submit, заголовок Idempotency-Key: уникальная сохраненная строка:

```json
{"expectedVersion":{{expectedVersion}},"confirmed":true}
```

Сохраните revisionId. Повторите с тем же фактическим ключом и версией:
тот же revisionId, replayed=true. confirmed=false →400; EDITOR →403.
GET /applications/{{applicationId}}/revisions/{{revisionId}} возвращает снимок/hash.

Банк: GET /bank/applications; POST /bank/applications/{{applicationId}}/assign;
POST /bank/applications/{{applicationId}}/process. Для полного примера, проверенных
документов, действующего макроконтекста и включенного DEMO ожидается APPROVED.
Проверьте decision.conditions.mode=DEMO, assessment.version=demo-fixed-weights-1,
isSimulated=true. Это фиксированная временная оценка, не реальный скоринг.
Без DEMO будет REQUEST_INFO/scoring; без макроконтекста — REQUEST_INFO/macroeconomic.key_rate_pct.

APPROVED создает offer. С ownerToken POST /applications/{{applicationId}}/offers/accept:
`{"offerId":"{{offerId}}","confirmed":true}`.
Затем POST /applications/{{applicationId}}/contract/sign: `{"confirmed":true}`.
Банк: POST /bank/applications/{{applicationId}}/disburse: `{"confirmed":true}`.
Ожидается DISBURSED, одна выдача; повтор →409, вторая запись не создается.

## 7. Встречное предложение — отдельный сценарий

Создайте новую форму: amount="2800000.00", revenue="6000000.00" за те же 12 месяцев.
В новой заявке monthlyDebtPayment="130000.00", overdue=0. Выберите P01,
проверьте документы, подайте и вызовите process при тестовом keyRatePct=10.
Ожидается COUNTEROFFERED, меньшая сумма, повышенная ставка и сохраненный срок 12 месяцев.

До акцепта поля offer нет. Сохраните counteroffer.id в proposalId и
counteroffer.termsSha256 в termsSha256. Проверьте alternative_terms и расчет:
новый платеж + 130000 <= 200000; сумма строго больше minAmount.
POST /applications/{{applicationId}}/counteroffers/accept:

```json
{"proposalId":"{{proposalId}}","termsSha256":"{{termsSha256}}","confirmed":true}
```

Ожидается OFFER_ACCEPTED и созданный offer с альтернативной суммой/ставкой.
Повтор должен вернуть тот же offer.id. Неправильный hash →409.
Изменение макроконтекста до акцепта не меняет сохраненные условия.
Исходная ревизия по-прежнему содержит 2800000.00. Договор и выдача используют альтернативу.

## 8. Дозапрос и обновление контекста

На новой заявке не задавайте overdue: после submit/process ожидается
REQUEST_INFO/NEEDS_INFO с financial.overdue. PATCH с актуальной expectedVersion
добавляет overdue; новый submit с новым ключом создает новую revisionId.
Старая ревизия/hash не меняются.

Если нужно дополнить поле предварительного этапа, например usageMode:
PATCH профиля → новый eligibility → новый selected-product. Затем в DRAFT/NEEDS_INFO
POST /applications/{{applicationId}}/refresh-preliminary:

```json
{"expectedVersion":{{expectedVersion}},"expectedProfileVersion":3}
```

Версии берите из фактических ответов. answers заявки не перезаписываются.
Для другого выбранного продукта нужна новая заявка.

## 9. Финансовые операции и ручная проверка

На новой DRAFT-заявке POST /applications/{{applicationId}}/financial-evidence:

```json
{"periodFrom":"2025-10-01","periodTo":"2026-09-30","operations":[
 {"externalId":"revenue-1","date":"2026-01-01","amount":"12000000.00","direction":"CREDIT","category":"REVENUE"},
 {"externalId":"loan-1","date":"2026-01-01","amount":"500000.00","direction":"CREDIT","category":"LOAN"}
]}
```

Ответ revenue=12000000.00: кредитные поступления не включаются. Повтор externalId →400.
GET /financial-evidence показывает операции и проверки. Сохраните evidenceId.
Банк: POST /bank/applications/{{applicationId}}/financial-evidence/{{evidenceId}}/review,
тело `{"result":"PASS","reason":"Проверены категории и период"}`.
Обновите rowVersion, подайте заявку. При заявленной выручке 24000000.00 ожидается
UNDER_REVIEW без окончательного Decision; journey.checks содержит REVIEW и reasonCode.
Банк может запросить уточнение через /decisions:

```json
{"kind":"REQUEST_INFO","reason":"Уточните расхождение выручки","missingFields":["financial.revenue"]}
```

Ожидается NEEDS_INFO. Клиент исправляет сведения и создает новую поданную ревизию.
UNKNOWN-категория или непроверенное доказательство дают дозапрос, а не нулевую выручку.

## Контроль каждого endpoint

Помимо последовательности выше, сверяйте результат каждого запроса с таблицей.
Для защищенных запросов повтор без Bearer →401, чужая компания/объект →404;
запись от VIEWER →403, банковская команда от клиента →403.

| Запрос | Основная проверка |
|---|---|
| `GET /health` | 200 status=ok после запроса к БД; доступ: No Auth. |
| `POST /auth/login` | 200 accessToken, tokenType, expiresAt; доступ: No Auth. |
| `POST /auth/logout` | 200; токен отозван; доступ: Любой пользователь. |
| `GET /me` | Пользователь, parties, bankApprover; доступ: Любой пользователь. |
| `GET /companies/{id}/profile` | Сведения доступной компании; доступ: Участник компании. |
| `GET /products` | Каталог действующих версий, totalElements; доступ: No Auth. |
| `GET /products/{id}` | Полные условия выбранной версии; доступ: No Auth. |
| `GET /forms/application` | 17 полей окончательной заявки и 13 transferredFields; доступ: Любой пользователь. |
| `POST /selection-profiles` | 15 полей, частичная форма; rowVersion, fieldSources, value_status; доступ: OWNER/EDITOR. |
| `GET /selection-profiles/{id}` | Форма подбора; изменение сбрасывает выбор продукта; доступ: Создатель и участник компании. |
| `PATCH /selection-profiles/{id}` | Форма подбора; изменение сбрасывает выбор продукта; доступ: Создатель OWNER/EDITOR. |
| `POST /applications` | DRAFT из выбранного профиля, отдельно preliminaryContext; доступ: OWNER/EDITOR. |
| `GET /applications` | Заявки доступных компаний; доступ: Участник компании. |
| `GET /applications/{id}` | Текущий черновик/статус/версия; доступ: Участник или банк. |
| `PATCH /applications/{id}` | Слияние ответов, версия +1; доступ: OWNER/EDITOR; DRAFT/NEEDS_INFO. |
| `POST /applications/{id}/validate` | value_status, review: kind/reason/conditions; доступ: Участник или банк. |
| `POST /applications/{id}/submit` | revisionId, sha256, replayed; доступ: OWNER. |
| `GET /applications/{id}/journey` | application, history, checks с причинами, decision, offer/counteroffer, договор/выдача; доступ: Участник или банк. |
| `GET /applications/{id}/status` | application, history, checks с причинами, decision, offer/counteroffer, договор/выдача; доступ: Участник или банк. |
| `GET /applications/{id}/revisions/{revision}` | snapshot, snapshot_sha256, revision_no; доступ: Участник или банк. |
| `GET /applications/{id}/requirements` | Требования продукта, включая поручительство и обеспечение; доступ: Участник или банк. |
| `POST /applications/{id}/documents` | versionId, sha256, value_status=UNKNOWN; доступ: OWNER/EDITOR; DRAFT/NEEDS_INFO. |
| `GET /applications/{id}/documents/{version}` | Закрытое скачивание PDF/PNG/JPEG/договора; доступ: Участник или банк. |
| `GET /bank/applications` | Банковская очередь; доступ: BANK_APPROVER. |
| `POST /bank/applications/{id}/assign` | assignedTo=текущий сотрудник; доступ: BANK_APPROVER. |
| `POST /bank/applications/{id}/process` | APPROVED/COUNTEROFFERED/DECLINED/REQUEST_INFO либо UNDER_REVIEW; положительные автоматические исходы только DEMO; доступ: Назначенный BANK_APPROVER. |
| `POST /bank/applications/{id}/decisions` | Ручное решение; не обходит документы, бюджет, оценку или жесткий отказ; доступ: Назначенный BANK_APPROVER. |
| `POST /bank/applications/{id}/documents/{version}/review` | Ручная CONTENT-проверка; доступ: BANK_APPROVER; DRAFT/SUBMITTED/NEEDS_INFO. |
| `POST /applications/{id}/offers/accept` | OFFER_ACCEPTED; доступ: OWNER. |
| `POST /applications/{id}/contract/sign` | SIGNED, условный договор; доступ: OWNER. |
| `POST /bank/applications/{id}/disburse` | DISBURSED, одна синтетическая запись; доступ: Назначенный BANK_APPROVER. |
| `GET /forms/preliminary` | 15 полей; 5 requiredForSelection; доступ: Любой пользователь. |
| `POST /selection-profiles/{id}/eligibility` | runId, profileVersion, причины; порядок по применимости/коду, personalRatingAvailable=false; доступ: OWNER/EDITOR. |
| `GET /selection-profiles/{id}/recommendations/{runId}` | Сохраненный результат; current=false после изменения формы; доступ: Участник компании. |
| `PUT /selection-profiles/{id}/selected-product` | Выбран продукт; rowVersion+1; старый run →409, INELIGIBLE →422; доступ: OWNER/EDITOR. |
| `POST /applications/{id}/refresh-preliminary` | Обновляет отдельный контекст того же профиля/продукта; answers не меняются; доступ: OWNER/EDITOR; DRAFT/NEEDS_INFO. |
| `POST /applications/{id}/counteroffers/accept` | Создает и принимает Offer по сохраненной альтернативе; повтор идемпотентен; доступ: OWNER. |
| `POST /bank/macroeconomic-contexts` | Неизменяемая версия серверной ставки 0..100; доступ: BANK_APPROVER. |
| `GET /bank/macroeconomic-contexts/current` | Действующий контекст; при отсутствии →422; доступ: BANK_APPROVER. |
| `POST /applications/{id}/financial-evidence` | id, вычисленная revenue, UNKNOWN; версия заявки+1; доступ: OWNER/EDITOR; DRAFT/NEEDS_INFO. |
| `GET /applications/{id}/financial-evidence` | Операции, периоды, расчетная выручка и результаты проверки; доступ: Участник или банк. |
| `POST /bank/applications/{id}/financial-evidence/{evidence}/review` | Новая неизменяемая банковская проверка; доступ: Назначенный BANK_APPROVER. |
| `GET /demo/scenarios` | 8 синтетических сценариев; только профиль demo и доступные компании; доступ: Участник или банк. |


## Границы и отрицательные сценарии

| Сценарий | Ожидание |
|---|---|
| overdue=true, "0.1", -0.1 или 1.1 | 400 |
| overdue=0.2 | Не является жестким запретом; дальнейший исход зависит от остальных данных |
| overdue=0.200000000001 | DECLINED, нет встречного предложения |
| Текущие платежи уже занимают 40% средней выручки | DECLINED: бюджета для положительной суммы нет |
| Недостаточный бюджет исходной суммы, но допустима меньшая | COUNTEROFFERED в DEMO при пройденных проверках |
| Нулевой знаменатель, нет выручки/периода | REQUEST_INFO, без Infinity/NaN |
| Неизвестный график платежей | REQUEST_INFO/product.paymentSchedule |
| Старый runId или версия формы | 409 |
| Выбор INELIGIBLE | 422 |
| Ручное APPROVED/COUNTEROFFERED в обход жесткого запрета/документов/оценки | 422 |
| Принять альтернативу по неправильному hash | 409 |
| Повторить акцепт той же альтернативы | Тот же Offer, без второй записи |
| Второй банковский сотрудник меняет закрепленную заявку | 409 |
| Изменить запечатанную заявку | 409 |
| Отозванный токен | 401 |

Маршруты подготовлены для ручной проверки. Автоматический прогон не называется
прогоном Postman: фактические результаты приведены в validation.md.


Новый сценарий ручного обмена и форма 2.0: [Query/Passage MVP — реализация](ranking-exchange.md).
