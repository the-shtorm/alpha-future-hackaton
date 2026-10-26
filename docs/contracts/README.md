# Контрактные примеры и схемы

[Навигация](../README.md) · [API](../backend-api.md)

| Файл | Назначение |
|---|---|
| [preliminary-2.0.example.json](preliminary-2.0.example.json) | 15 полей предварительной формы, объект `answers` |
| [application-3.0-additions.example.json](application-3.0-additions.example.json) | Четыре дополнения при создании полной заявки |
| [ranking-response.schema.json](ranking-response.schema.json) | Структура ответа ранжирования для Java |
| [scoring-request.schema.json](../../fastapi/contracts/scoring-request.schema.json) | Вход SBA-скоринга |
| [scoring-response.schema.json](../../fastapi/contracts/scoring-response.schema.json) | Выход SBA-скоринга |
| [openapi.json](../../fastapi/contracts/openapi.json) | Зафиксированный OpenAPI ML-сервиса |

Полный список полей: [backend-fields-v3.md](../backend-fields-v3.md).
Примеры показывают форму данных; актуальные UUID, даты периода, версии и
идентификаторы берутся из своего запущенного экземпляра. Авторитетные текущие
схемы Java доступны через `/forms/preliminary`, `/forms/application` и `/v3/api-docs`.
