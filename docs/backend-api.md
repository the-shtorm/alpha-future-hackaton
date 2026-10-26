> Актуальная схема: [Preliminary Form 2.0 / Data Policy 3.0](backend-fields-v3.md). Изменены поля; алгоритм ML 3.0 не реализован.

# REST API: Data Policy 2.1 и Preliminary Form 2.0

Base URL: `http://localhost:8080`, учитывайте BACKEND_PORT из .env.
Swagger: `/swagger-ui/index.html`; OpenAPI: `/v3/api-docs`.
JSON-команды: Content-Type application/json. Браузер использует HttpOnly-cookie через
same-origin `/api` на frontend; интеграционные клиенты сохраняют Bearer accessToken из `/auth/login`.
Сессия действует 12 часов с момента входа, в БД хранится SHA-256; logout отзывает текущую сессию.
Автоматического бессрочного продления нет. Состояние сессий общее для Java-реплик в PostgreSQL;
HttpSession/JSESSIONID и sticky sessions не используются. Миграция БД не требуется.
Все успешные операции ниже возвращают 200. Health/login/CSRF/catalog/Swagger доступны без входа.

Браузерный вход:
1. `GET /api/auth/csrf` с `credentials: same-origin`: сервер выставит HttpOnly CSRF-cookie,
   JSON вернёт `headerName: X-XSRF-TOKEN` и маскированный `token`.
2. `POST /api/auth/session` с JSON `login/password`, cookie и заголовком `X-XSRF-TOKEN`
   из шага 1. Ответ содержит `status/expiresAt`, идентификатор сессии передаётся только в HttpOnly-cookie.
3. После входа снова получить `/auth/csrf`: при входе/выходе CSRF меняется. Все изменяющие
   запросы с cookie, включая multipart, отправляют этот заголовок; без него — 403 `CSRF_INVALID`.
   Обычные GET и Bearer-запросы к API не требуют CSRF; `/auth/session` защищён всегда.
4. При загрузке страницы вызвать `/me`. 401 означает завершение сессии; сетевой сбой
   не считается logout. Фронтенд хранит в URL только экран и UUID ресурсов, секреты в Web Storage не пишет.
5. `POST /auth/logout` с CSRF отзывает сессию и удаляет cookie. Повторный вход меняет
   идентификатор и отзывает предыдущую cookie-сессию, неверный пароль её не отзывает.

Cookie имеют Path=/, HttpOnly, SameSite=Lax, без Domain. По умолчанию Java использует
Secure и префикс `__Host-` (`__Host-ALPHA_SESSION`, `__Host-ALPHA_CSRF`).
Локальный HTTP Compose явно задаёт `SESSION_COOKIE_SECURE=false` (`ALPHA_SESSION`, `ALPHA_CSRF`).
При размещении за HTTPS задайте `SESSION_COOKIE_SECURE=true`; фронтенд и `/api` должны
быть на одном origin. Смена режима Secure потребует повторного входа. При одновременной
передаче Authorization и cookie выбирается только Authorization, даже если он невалиден.

Браузер автоматически сохраняет обе формы после входа через существующие POST/PATCH с
expectedVersion; запросы сериализуются. До входа хранится только предварительная форма
в текущей вкладке, до 24 часов, без токенов/паролей/идентификаторов ресурсов. После
успешного переноса на сервер или выхода локальный черновик удаляется. Конфликт 409
не перезаписывается автоматически. Незавершённое сохранение защищено предупреждением
при закрытии/обновлении; переходы по разделам дожидаются записи. Отправка заявки
остаётся отдельным явным действием и требует подтверждения.
Локальная проверка Secure-cookie/TLS: `python3 scripts/check_cookie_https.py` после
сборки штатных backend/frontend образов; скрипт удаляет только собственный тестовый стек.

[Типы и расчеты](data-dictionary.md), [источники требований](data-policy.md),
[предварительная форма](preliminary_form.md), [Postman](postman-testing.md).

| Метод | Endpoint | Вход | Результат | Доступ |
|---|---|---|---|---|
| GET | `/health` | Нет | 200 status=ok после запроса к БД | No Auth |
| POST | `/auth/login` | login, password | 200 accessToken, tokenType, expiresAt | No Auth |
| GET | `/auth/csrf` | Нет | CSRF cookie и JSON headerName/token | No Auth |
| POST | `/auth/session` | login, password + CSRF | HttpOnly session cookie, status, expiresAt | No Auth + CSRF |
| POST | `/auth/logout` | Нет | 200; токен отозван | Любой пользователь |
| GET | `/me` | Нет | Пользователь, parties, bankApprover | Любой пользователь |
| GET | `/companies/{id}/profile` | Нет | Сведения доступной компании | Участник компании |
| GET | `/products` | page=0, size=12 (1..50) | Каталог действующих версий, totalElements | No Auth |
| GET | `/products/{id}` | UUID продукта или версии | Полные условия выбранной версии | No Auth |
| GET | `/forms/application` | Нет | 17 полей окончательной заявки и 13 transferredFields | Любой пользователь |
| POST | `/selection-profiles` | partyId, answers | 15 полей, частичная форма; rowVersion, fieldSources, value_status | OWNER/EDITOR |
| GET | `/selection-profiles/{id}` | Нет | Форма подбора; изменение сбрасывает выбор продукта | Участник компании |
| PATCH | `/selection-profiles/{id}` | expectedVersion, answers | Форма подбора; изменение сбрасывает выбор продукта | OWNER/EDITOR |
| POST | `/applications` | profileId, expectedProfileVersion, answers (дополнения по схеме 17 полей) | DRAFT из выбранного профиля, отдельно preliminaryContext | OWNER/EDITOR |
| GET | `/applications` | page, size | Заявки доступных компаний | Участник компании |
| GET | `/applications/{id}` | Нет | Текущий черновик/статус/версия | Участник или банк |
| PATCH | `/applications/{id}` | expectedVersion, answers | Слияние ответов, версия +1 | OWNER/EDITOR; DRAFT/NEEDS_INFO |
| POST | `/applications/{id}/validate` | Нет | value_status, review: kind/reason/conditions | Участник или банк |
| POST | `/applications/{id}/submit` | expectedVersion, confirmed=true; Idempotency-Key | revisionId, sha256, replayed | OWNER |
| GET | `/applications/{id}/journey` | Нет | application, history, checks с причинами, decision, offer/counteroffer, договор/выдача | Участник или банк |
| GET | `/applications/{id}/status` | Нет | application, history, checks с причинами, decision, offer/counteroffer, договор/выдача | Участник или банк |
| GET | `/applications/{id}/revisions/{revision}` | Нет | snapshot, snapshot_sha256, revision_no | Участник или банк |
| GET | `/applications/{id}/requirements` | Нет | Требования продукта, включая поручительство и обеспечение | Участник или банк |
| GET | `/applications/{id}/documents` | Нет | Версии файлов, current, versionNo и последний результат проверки; без storage_key | Участник или BANK_APPROVER |
| POST | `/applications/{id}/documents` | multipart: typeCode, file, опционально replacesVersionId | versionId, sha256, value_status=UNKNOWN | OWNER/EDITOR; DRAFT/NEEDS_INFO |
| GET | `/applications/{id}/documents/{version}` | Нет | Закрытое скачивание PDF/PNG/JPEG/договора | Участник или банк |
| GET | `/bank/applications` | page, size | Банковская очередь | BANK_APPROVER |
| POST | `/bank/applications/{id}/assign` | Нет | assignedTo=текущий сотрудник | BANK_APPROVER |
| POST | `/bank/applications/{id}/process` | Нет | APPROVED/COUNTEROFFERED/DECLINED/REQUEST_INFO либо UNDER_REVIEW; положительные автоматические исходы только DEMO | Назначенный BANK_APPROVER |
| POST | `/bank/applications/{id}/decisions` | kind, reason, missingFields | Ручное решение; не обходит документы, бюджет, оценку или жесткий отказ | Назначенный BANK_APPROVER |
| POST | `/bank/applications/{id}/documents/{version}/review` | result=PASS/FAIL/UNKNOWN, reason | Ручная CONTENT-проверка | BANK_APPROVER; DRAFT/SUBMITTED/NEEDS_INFO |
| POST | `/applications/{id}/offers/accept` | offerId, confirmed=true | OFFER_ACCEPTED | OWNER |
| POST | `/applications/{id}/contract/sign` | confirmed=true | SIGNED, условный договор | OWNER |
| POST | `/bank/applications/{id}/disburse` | confirmed=true | DISBURSED, одна синтетическая запись | Назначенный BANK_APPROVER |
| GET | `/forms/preliminary` | Нет | 15 полей; 5 requiredForSelection | Любой пользователь |
| POST | `/selection-profiles/{id}/eligibility` | Нет | runId, profileVersion, причины; порядок по применимости/коду, personalRatingAvailable=false | OWNER/EDITOR |
| GET | `/selection-profiles/{id}/recommendations/{runId}` | Нет | Сохраненный результат; current=false после изменения формы | Участник компании |
| PUT | `/selection-profiles/{id}/selected-product` | expectedVersion, runId, productVersionId | Выбран продукт; rowVersion+1; старый run →409, INELIGIBLE →422 | OWNER/EDITOR |
| POST | `/applications/{id}/refresh-preliminary` | expectedVersion, expectedProfileVersion | Обновляет отдельный контекст того же профиля/продукта; answers не меняются | OWNER/EDITOR; DRAFT/NEEDS_INFO |
| POST | `/applications/{id}/counteroffers/accept` | proposalId, termsSha256, confirmed=true | Создает и принимает Offer по сохраненной альтернативе; повтор идемпотентен | OWNER |
| POST | `/bank/macroeconomic-contexts` | keyRatePct (строка), validFrom, expiresAt, sourceCode | Неизменяемая версия серверной ставки 0..100 | BANK_APPROVER |
| GET | `/bank/macroeconomic-contexts/current` | Нет | Действующий контекст; при отсутствии →422 | BANK_APPROVER |
| POST | `/applications/{id}/financial-evidence` | periodFrom, periodTo, operations[] | id, вычисленная revenue, UNKNOWN; версия заявки+1 | OWNER/EDITOR; DRAFT/NEEDS_INFO |
| GET | `/applications/{id}/financial-evidence` | Нет | Операции, периоды, расчетная выручка и результаты проверки | Участник или банк |
| POST | `/bank/applications/{id}/financial-evidence/{evidence}/review` | result=PASS/FAIL/UNKNOWN, reason | Новая неизменяемая банковская проверка | Назначенный BANK_APPROVER |
| GET | `/demo/scenarios` | Нет | 8 синтетических сценариев; только профиль demo и доступные компании | Участник или банк |

## Переход от формы к заявке

При известной выручке перед подбором нужны обе даты полного периода (первое и
последнее число месяца); иначе 400 INVALID_INPUT. Запуски до eligibility-3.1
сохраняются в истории, но требуют повторного подбора перед выбором продукта,
обменом ранжированием и созданием заявки (409 SELECTION_STALE).

1. POST /selection-profiles с partyId и 15-польной формой.
2. POST /selection-profiles/{id}/eligibility: сохранить runId.
3. PUT /selection-profiles/{id}/selected-product с текущей expectedVersion и выбранной версией.
4. POST /applications:

```json
{
  "profileId":"UUID профиля",
  "expectedProfileVersion":1,
  "answers":{
    "financial":{"monthlyDebtPayment":"0.00","overdue":0},
    "security":{"collateralValue":"0.00"},
    "project":{"ownContributionPct":"0.00"}
  }
}
```

Сервер переносит ровно 13 общих полей. Дополнения/редактирование принимаются только по
17-польной схеме заявки. partyId/productVersionId/status/fieldSources не подменяются клиентом.
Отдельный preliminaryContext хранит источник выбора. После PATCH формы выбор сбрасывается;
старый результат сохраняется и не может использоваться для нового выбора.

PATCH заявки: expectedVersion и answers; null удаляет поле, массивы не являются полями анкеты.
В DRAFT/NEEDS_INFO можно явно обновить контекст того же профиля через refresh-preliminary;
текущие 17 ответов при этом не перезаписываются.

## Подача и банковская обработка

OWNER: submit с expectedVersion, confirmed=true и Idempotency-Key длиной 1..160.
Перед отправкой перечитайте rowVersion после загрузки документа или финансового доказательства.
Повтор идентичного ключа/версии возвращает прежний revisionId, replayed=true.
Новый submit после NEEDS_INFO создает новую ревизию, не изменяет предыдущую.

validate возвращает предварительный расчет/качество данных, не сохраненное банковское решение.
process выполняется для SUBMITTED (или продолжает UNDER_REVIEW) назначенным BANK_APPROVER.
Просрочка>0.2 запрещает встречное предложение. Пропуски/UNKNOWN-документы дают REQUEST_INFO
и NEEDS_INFO. Проверенное расхождение операций и выручки или короткая история могут
дать UNDER_REVIEW без окончательного Decision; причины находятся в journey.checks[].evidence.

Новые ревизии используют `data-policy-3.0-sba-annuity-1` и обученный SBA CatBoost.
`conditions` содержит `sbaDefaultProbability`, `finalRiskScore`, `pti`, `selectedVariant`,
версии, `warnings`, `scoringAssessments` и `assessmentIds`; FK решения указывает
на выбранную оценку. Риск политики не является автоматически калиброванной PD.
При сбое модели или попытке использовать её для несинтетического продукта —
REQUEST_INFO/ASSESSMENT_UNAVAILABLE, подробный код в `scoringErrorCode`.
Отсутствие макроконтекста — REQUEST_INFO/macroeconomic.key_rate_pct.
Исторические ревизии сохраняют 2.1, старые решения/предложения не пересчитываются.
Контракт и правила: [кредитный скоринг](credit-scoring.md).

Ручное решение:

```json
{"kind":"REQUEST_INFO","reason":"Уточните расхождение выручки","missingFields":["financial.revenue"]}
```

APPROVED/COUNTEROFFERED ручной командой разрешены только если текущая проверка дает
соответствующий положительный результат; обязательные проверки нельзя обходить ролью банка.
REQUEST_INFO требует missingFields. DECLINED требует причину. Источник сохраняется BANK_APPROVER.

## Встречное предложение

Decision.kind=COUNTEROFFERED; alternative_terms содержит amount/termMonths/annualRatePct.
В journey.counteroffer: id, termsSha256, expiresAt и те же alternative_terms.
Offer до акцепта не создается. OWNER подтверждает:

```json
{"proposalId":"UUID альтернативы","termsSha256":"64 символа из ответа","confirmed":true}
```

Условия не пересчитываются при акцепте. Другой hash —409; чужой объект —404;
просроченная/устаревшая альтернатива —409. Создание Offer и acceptance атомарно,
повтор возвращает тот же Offer. Далее contract/sign и банковская disburse используют
новую сумму/ставку, а не исходные answers. Смена ключевой ставки старую альтернативу не меняет.
Для обычного APPROVED Offer создается сразу и принимается через offers/accept.
Срок предложения 7 дней; договор и выдача синтетические, повторная выдача —409.

## Макроконтекст

Создается банком, не в answers клиента. Пример **искусственных** данных:

```json
{"keyRatePct":"10.00000","validFrom":"2026-10-01T00:00:00Z","expiresAt":"2026-11-01T00:00:00Z","sourceCode":"DEMO_FIXTURE_NOT_CBR"}
```

При проверке используйте действующие даты. Это не реальная ставка ЦБ. Нет автоматического
получения ставки; sourceCode и период задаются явно. Записи защищены от UPDATE/DELETE.

## Документы и операции

Документы: multipart typeCode+file, PDF/PNG/JPEG по сигнатуре, максимум 10 MB.
CREDIT_CONTRACT зарезервирован сервером. При загрузке UNKNOWN, банковский CONTENT PASS
фиксируется отдельной записью; роль клиента не позволяет подтвердить документ.
Требования зависят от продукта: например P01 для LLC требует GUARANTEE_CONTRACT.
Файлы можно скачивать только с доступом к заявке. Неизвестный/чужой versionId —404.

Финансовое доказательство отдельно от answers:

```json
{
  "periodFrom":"2025-10-01","periodTo":"2026-09-30",
  "operations":[{"externalId":"op-1","date":"2026-01-01","amount":"24000000.00","direction":"CREDIT","category":"REVENUE"}]
}
```

Допустимые направления CREDIT/DEBIT; категории REVENUE/REVENUE_REFUND/INTERNAL_TRANSFER/
LOAN/EXPENSE/UNKNOWN. До 10000 операций, идентификаторы без повторов, даты внутри периода.
Неизвестные категории или отсутствие PASS дают дозапрос. Проверенное расхождение с
заявленной выручкой отправляет на ручное рассмотрение. GET позволяет банку видеть операции.

## Ошибки

application/problem+json содержит code/detail/fields без SQL, токенов или путей хранилища.
400 — формат/тип/подтверждение; 401 — сессия; 403 — роль; 404 — чужой/нет объекта;
409 — версия, статус, чужое назначение, hash или идемпотентность;
413 — размер файла; 422 — запрет выбора/одобрения или отсутствие макроконтекста;
503 — недоступный файл. Машинные причины бизнес-проверок — conditions.reasonCode и eligibility.reasons.


Новый сценарий ручного обмена и форма 2.0: [Query/Passage MVP — реализация](ranking-exchange.md).


## Ручное ранжирование MVP

| Метод | Endpoint | Результат | Доступ |
|---|---|---|---|
| GET | `/forms/preliminary/dictionaries` | Общие словари целей, отраслей, использования и readiness | Авторизованный пользователь |
| GET | `/selection-profiles/{id}/recommendations/{runId}/ranking-export` | Снимок формы, queryFields, допустимые версии и предупреждения | Член компании |
| POST | `/selection-profiles/{id}/recommendations/{runId}/ranking-result` | Проверка и неизменяемое сохранение внешнего порядка/similarityScore | OWNER/EDITOR |
| GET | `/selection-profiles/{id}/recommendations/{runId}/ranking-result` | Сходство вместе с исходными eligibilityStatus/pendingConditions | Член компании |

Тело ответа команды и ошибки: [контракт обмена](ranking-exchange.md).

Замена документа задаётся явно через `replacesVersionId` последней версии этого файла.
Тип и заявка должны совпадать; устаревшая версия даёт 409. Без этого параметра
добавляется отдельный документ. Новая подача фиксирует последние версии каждого
документа; старые ревизии и файлы сохраняются. Проверка старой версии не меняет
статус требования для её новой версии.
