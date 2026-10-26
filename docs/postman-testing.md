# Пошаговая проверка REST API

[Навигация](README.md) · [Запуск Docker](hackathon-start.md) · [Полный API](backend-api.md)

## Окружение

Запустите Compose по основной инструкции. В Postman создайте `baseUrl=http://localhost:8080`.
Для проверки прокси используйте `http://localhost:3000/api`. Пароли возьмите из
своего `.env`: клиент `demo-owner` / `DEMO_PASSWORD`, банк `demo-bank` /
`DEMO_BANK_PASSWORD`. Не сохраняйте реальные секреты в экспортируемую коллекцию.

JSON-команды отправляются с `Content-Type: application/json`. Для Bearer-сценария
выполните два `POST {{baseUrl}}/auth/login` с `login`/`password` и сохраните
`accessToken` как локальные `ownerToken` и `bankToken`. Выбирайте соответствующий
Bearer token в каждом запросе. Браузерный cookie/CSRF-вход отдельно описан в
[API](backend-api.md); Postman может воспроизвести его через cookie jar.

## 1. Проверка готовности и исходные данные

1. `GET /health` → `status=ok`.
2. Под owner: `GET /me` → доступные компании; сохраните `partyId`.
3. `GET /products?size=50` → каталог; найдите P07 и сохраните его `versionId`.
4. `GET /forms/preliminary` и `/forms/application` → схемы 15 и 17 полей.
5. `GET /demo/scenarios` → синтетические примеры; STABLE даёт готовый объект
   предварительных ответов и дополнений с актуальным периодом выручки.

Под bank создайте действующий учебный макроконтекст:

```json
{
  "keyRatePct": "10.00000",
  "validFrom": "2026-10-26T00:00:00Z",
  "expiresAt": "2026-11-26T00:00:00Z",
  "sourceCode": "DEMO_HACKATHON"
}
```

URL: `POST /bank/macroeconomic-contexts`. Замените даты так, чтобы
`validFrom <= сейчас < expiresAt`. `GET /bank/macroeconomic-contexts/current`
возвращает действующий контекст.

## 2. Форма и автоматический подбор

Под owner выполните `POST /selection-profiles`:

```json
{
  "partyId": "PARTY_UUID",
  "answers": {
    "registration": {"borrowerKind": "LLC"},
    "business": {"sector": "TRADE", "actualStartedOn": "2020-01-01", "taxRegime": "USN", "mspRegistry": false},
    "financial": {"revenue": "24000000.00", "periodFrom": "2025-10-01", "periodTo": "2026-09-30"},
    "request": {"purpose": "EQUIPMENT", "amount": "500000.00", "termMonths": 60, "usageMode": "ONE_TIME", "description": "Покупка оборудования для учебной компании"},
    "security": {"collateralReady": "YES", "guarantorReady": "YES"}
  }
}
```

Укажите последние 12 полных календарных месяцев относительно дня проверки.
Сохраните `profileId` и `rowVersion`.

`POST /selection-profiles/{profileId}/automatic-selection` с `{}` запускает
проверку применимости и E5. Ожидается `rankingStatus=READY`, ранжированные
`results`, максимум три выделенные рекомендации. Сохраните `runId`.

Выберите P07: `PUT /selection-profiles/{profileId}/selected-product`:

```json
{"expectedVersion": 0, "runId": "RUN_UUID", "productVersionId": "P07_VERSION_UUID"}
```

`expectedVersion` замените фактической версией формы; сохраните новую версию ответа.

## 3. Создание, документы и подача

`POST /applications`:

```json
{
  "profileId": "PROFILE_UUID",
  "expectedProfileVersion": 1,
  "answers": {
    "financial": {"monthlyDebtPayment": "0.00", "overdue": 0},
    "security": {"collateralValue": "1000000.00"},
    "project": {"ownContributionPct": "20.00"}
  }
}
```

Подставьте версию выбранной формы из предыдущего ответа. Проверьте перенос 13
полей, отдельный `preliminaryContext` и `status=DRAFT`.

`GET /applications/{id}/requirements` возвращает `type_code` требуемых файлов.
Для каждого выполните `POST /applications/{id}/documents`, body `form-data`:
`typeCode=<код требования>`, `file=<docs/demo/sample-document.pdf>`.
Postman сам установит multipart boundary. Сохраните `versionId`.
`GET /applications/{id}/documents` показывает версии; бинарный GET
`/applications/{id}/documents/{versionId}` скачивает файл.

Для замены файла в DRAFT/NEEDS_INFO отправьте тот же multipart с
`replacesVersionId=<текущая versionId>`. История содержит старую и новую версии,
`current=true` у новой. В дальнейшую проверку и ревизию входит актуальная версия.

Перед подачей перечитайте `GET /applications/{id}`. `POST /applications/{id}/submit`:

```json
{"expectedVersion": 4, "confirmed": true}
```

Подставьте фактическую `rowVersion`. Добавьте `Idempotency-Key` с новым UUID.
Сохраните `revisionId`; повтор той же команды возвращает `replayed=true`.

## 4. Рассмотрение банком

Под bank:

1. `GET /bank/applications` — очередь.
2. `POST /bank/applications/{id}/assign` с `{}` — назначение себе.
3. Для текущих файлов `POST /bank/applications/{id}/documents/{versionId}/review`:
   `{"result":"PASS","reason":"Проверка учебного документа"}`.
4. `POST /bank/applications/{id}/process` с `{}` — проверки и SBA-скоринг.
5. `GET /applications/{id}/journey` — история, проверки и решение.

Для указанных данных P07 ожидается `decision.kind=APPROVED` и обычный `offer`.
В `conditions` видны версия `sba-scoring-v2`, `data-policy-3.0-sba-annuity-1`,
вероятность, PTI и сохранённая оценка.

## 5. Акцепт, договор и выдача

Под owner `POST /applications/{id}/offers/accept`:
`{"offerId":"OFFER_UUID","confirmed":true}` → `OFFER_ACCEPTED`.
Затем `POST /applications/{id}/contract/sign` с `{"confirmed":true}` → `SIGNED`.
Под bank `POST /bank/applications/{id}/disburse` с тем же подтверждением →
`DISBURSED`. `journey` содержит договор, выдачу и историю переходов.
Договор и выдача относятся к демонстрационному сценарию.

## Другие исходы и повторяемость

Для каждого варианта создавайте новый профиль и заявку. Данные P01 и ожидаемые
исходы `COUNTEROFFERED`, `DECLINED`, `REQUEST_INFO` приведены в
[инструкции проверяющего](hackathon-start.md). Встречное предложение принимается
через `POST /applications/{id}/counteroffers/accept` с `proposalId`,
`termsSha256`, `confirmed=true`, после чего выполняются те же подписание и выдача.

Проверки контракта: устаревший `expectedVersion` → 409; посторонняя компания → 404;
неизвестное поле или неверный тип → 400; отсутствие входа → 401. Изменение формы
требует нового подбора. Завершение сессии: `POST /auth/logout`.
