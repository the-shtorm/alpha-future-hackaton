# Обмен рекомендациями Java и FastAPI

[Навигация](README.md) · [Query/Passage](query_passage_mvp.md) · [E5](../fastapi/MODEL_HANDOFF.md)

## Автоматический путь

Frontend вызывает `POST /selection-profiles/{id}/automatic-selection`. Spring
создаёт снимок проверки применимости, передаёт допустимых кандидатов в
`POST /api/v1/recommendations/rank-java` и сохраняет проверенный ответ.
`rankingStatus=READY` означает доступность ранжированного результата.
История содержит версии формы, продуктов, модели и текстовых шаблонов.

Повтор вызова для существующего runId:
`POST /selection-profiles/{id}/recommendations/{runId}/retry`. Состояния попыток
хранятся в `recommendation_attempt`. После изменения формы требуется новый подбор.
Клиент выбирает версию продукта через `PUT /selection-profiles/{id}/selected-product`
с `expectedVersion`, `runId` и `productVersionId`; затем создаёт заявку.

Java использует `RECSYS_URL`, таймаут `RECSYS_TIMEOUT_MS` и внутренний Bearer
`RECSYS_API_KEY`. FastAPI и Java получают один и тот же ключ из `.env`.
Сервис работает на CPU; ML-порт доступен внутри Compose-сети.

## Запрос

`schemaVersion=query-passage-mvp-2`, `semanticsVersion=synthetic-semantics-1`.

| Поле | Содержание |
|---|---|
| `requestId` | UUID проверки, совпадает с runId |
| `profileId`, `profileVersion` | Источник и версия формы |
| `profile` | Снимок предварительных ответов |
| `queryFields` | sector, purpose, usageMode, description, collateralReady, guarantorReady |
| `dictionaries` | Версия и подписи общих кодов |
| `candidates` | Все ELIGIBLE/CONDITIONAL с productId, productVersion, product, checks, pendingConditions |
| `topK` | 3 |
| `scoreMeaning` | `COSINE_SIMILARITY_NOT_APPROVAL_PROBABILITY` |

`product` содержит закреплённые смысловые поля: код, название, тип, цели,
способы использования, сценарий, отрасли, специализацию и условия обеспечения.
Ограничения суммы, срока, выручки и статуса бизнеса проверяет Spring.

## Ответ и проверки

```json
{
  "requestId": "UUID_FROM_REQUEST",
  "metadata": {
    "model": "local/e5-credit-finetune-v1",
    "modelVersion": "ACTUAL_MODEL_VERSION",
    "queryTemplateVersion": "ACTUAL_QUERY_TEMPLATE",
    "passageTemplateVersion": "ACTUAL_PASSAGE_TEMPLATE"
  },
  "results": [
    {
      "productId": "CANDIDATE_PRODUCT_UUID",
      "productVersion": "CANDIDATE_VERSION_UUID",
      "rank": 1,
      "similarityScore": 0.8123456789,
      "isRecommended": true,
      "eligibilityStatus": "ELIGIBLE",
      "pendingConditions": []
    }
  ]
}
```

Пример содержит placeholders; реальные UUID, версии, статусы и условия берутся
из текущего запроса. `metadata` заполняется runtime-моделью и шаблонами.

Результат включает каждого кандидата ровно один раз. Ранги — целые `1..N`,
score — конечное JSON-число в `[-1,1]`, не возрастающее с ростом ранга.
`eligibilityStatus` и `pendingConditions` возвращаются без изменения, включая
порядок условий. Флаг рекомендации выделяет подходящие первые результаты,
максимум `topK=3`, с учётом активного порога cosine distance. Пустой список
кандидатов допускает `results: []`. UI показывает score с четырьмя знаками.

Схема ответа: [ranking-response.schema.json](contracts/ranking-response.schema.json).
Полнота кандидатов, эхо применимости, ранги и актуальность дополнительно
проверяются Java. Сохранённый ответ неизменяем: эквивалентный повтор идемпотентен,
другой ответ для того же runId возвращает `RANKING_ALREADY_IMPORTED`.
Изменение формы даёт `SELECTION_STALE`, изменение активного каталога — `CATALOG_STALE`.
Исторический результат можно читать с `current=false`.

## Технический экспорт и импорт

Для интеграции доступны те же снимки и строгие проверки:

| Метод | URL после `/selection-profiles/{id}/recommendations/{runId}` |
|---|---|
| GET | `/ranking-export` |
| POST | `/ranking-result` |
| GET | `/ranking-result` |

Экспорт/чтение разрешены участникам компании, импорт — OWNER/EDITOR.
JSON неизвестных полей, чужих кандидатов или изменённых условий отклоняется.
Штатный пользовательский путь выполняет обмен автоматически.
