# Реализованная схема PostgreSQL

[Навигация](README.md) · [Хранение форм](form-storage-contract.md) · [ERD](database-erd.mmd)

PostgreSQL 17 хранит данные в схеме `credit`. Источник истины — Flyway-миграции
`backend/src/main/resources/db/migration/`, версии V1–V11. При первом запуске
Compose init-скрипты создают `credit_migrator` и `credit_app`; Java выполняет
Flyway отдельной миграционной ролью и работает через прикладную роль.

## Группы таблиц

| Группа | Таблицы и назначение |
|---|---|
| Идентификация | `app_user`, `user_role`, `api_session`: пользователи, роли и hash сессий |
| Компании | `party`, `party_membership`, `party_relation`, `business_profile` |
| Каталог | `credit_product`, `credit_product_version`: продукт и закреплённые условия |
| Подбор | `preliminary_profile`, `recommendation_run`, `recommendation_item` |
| Ранжирование | `manual_ranking_result`, `recommendation_attempt`: неизменяемый ответ E5 и попытки обмена |
| Заявка | `loan_application`, `application_party`, `application_revision`, `api_submission` |
| Финансы | `financial_statement`, `application_financial_evidence`, `financial_evidence_review` |
| Документы | `document_type`, `document`, `document_version`, `document_review` |
| Требования | `application_document_requirement`, `requirement_document`, `revision_document` |
| Проверки | `application_check_requirement`, `check_run`, `assessment_run` |
| Решения | `credit_decision`, `loan_offer`, `counteroffer_proposal`, `counteroffer_acceptance` |
| Макроконтекст | `macroeconomic_context`: ставка, источник, начало и окончание действия |
| Завершение | `loan_contract`, `disbursement` |
| История | `application_status_history`, `audit_event` |
| Дополнительные структуры досье | `consent`, `consent_revocation`, `external_request`, `outbox_event` |

Последняя группа описывает существующие структуры хранения; текущий интерактивный
путь и HTTP-операции перечислены в [архитектуре](backend-plan.md) и [API](backend-api.md).
Файлы находятся в `documents_data`; БД хранит ссылки, тип, размер, digest и версии.

## Эволюция схемы

| Миграция | Содержание |
|---|---|
| V1 | Пользователи, компании, каталог, предварительные формы и подбор |
| V2 | Заявки, ревизии, документы, проверки, решения, предложение, договор, выдача и аудит |
| V3 | Проверки целостности, неизменяемости и история переходов |
| V4 | Каталог документов и права прикладной роли |
| V5 | API-сессии, идемпотентная подача и выбор продукта |
| V6 | Режим обработки заявки |
| V7 | Редактируемые ответы и Data Policy 2.1 |
| V8 | Раздельные формы, preliminaryContext, макроконтекст и встречные условия |
| V9 | Финансовые доказательства и защита контекста |
| V10 | Сохранение результата ранжирования |
| V11 | Попытки автоматического вызова рекомендательной системы |

Точные имена и DDL смотрите в файлах миграций. Повторяемые demo-миграции
добавляют синтетические компании, пользователей и продукты при профиле `demo`.
Пароли демо-пользователей задаются при запуске через окружение.

## Целостность и доступ

UUID идентифицируют сущности. JSONB хранит версионированные ответы, условия,
снимки и evidence. `row_version` обеспечивает optimistic locking черновиков.
Внешние ключи связывают решение с оценкой и ревизией, предложение — с решением,
договор — с принятым предложением, выдачу — с договором.

Триггеры защищают неизменяемые снимки, макроконтекст, историю и допустимые переходы;
контроль документов и проверок применяется к соответствующему этапу. Банк и клиент
дополнительно авторизуются Java по роли и членству в компании. Секрет сессии
в БД представлен SHA-256; исходный идентификатор не сохраняется.

## Эксплуатация

Compose использует `postgres_data`; обычный `docker compose down` сохраняет данные.
`down --volumes` удаляет тома проекта, поэтому для повторяемого теста предпочтителен
отдельный `--project-name` и собственный env-файл. В pgAdmin (`localhost:5050`)
сервер внутри Compose доступен как `postgres:5432`, БД — `credit_cabinet`,
прикладная роль — `credit_app`, пароль — `DB_APP_PASSWORD` из своего env-файла.
Подробная инструкция: [запуск](hackathon-start.md).
