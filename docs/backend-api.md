# REST API — контракт MVP

Java API по умолчанию: `http://localhost:8080` (текущий локальный `.env`: порт 8081); Swagger: `/swagger-ui/index.html`, OpenAPI: `/v3/api-docs`.
Все маршруты, кроме `/health`, документации, входа, каталога, поиска бизнеса и анонимных профилей,
требуют `Authorization: Bearer <token>`. Токен возвращает `POST /auth/login` и действует 12 часов.
Пароли проверяются через Spring PasswordEncoder; cookie-сессии не используются.
`POST /auth/logout` отзывает текущий токен. `GET /me` возвращает пользователя и его организации.

| Метод | Маршрут | Назначение |
|---|---|---|
| GET | /products | Каталог: page=0, size=12 (1…50), sort=name,asc; purpose, amount, termMonths, borrowerKind, collateralRequired |
| GET | /products/{id} | Полные действующие условия продукта |
| POST | /business/lookup | Проверенный по контрольным разрядам taxId, ответ локального синтетического источника |
| POST | /selection-profiles | Создать профиль: `{"answers":{...}}` |
| GET | /selection-profiles/{id} | Прочитать свой профиль |
| PATCH | /selection-profiles/{id} | `{"expectedVersion":0,"answers":{...}}`: рекурсивное слияние, null удаляет поле |
| POST | /selection-profiles/{id}/eligibility | Проверка всех действующих продуктов, неизменяемый снимок правил и профиля |
| PUT | /selection-profiles/{id}/selected-product | `{"expectedVersion":0,"productVersionId":"uuid"}` |
| POST | /applications | Черновик из профиля: profileId, partyId; проверка членства и выбора продукта |
| GET | /applications | Заявки доступных организаций, пагинация |
| GET/PATCH | /applications/{id} | Чтение/обновление черновика; PATCH: expectedVersion, answers |
| GET | /applications/{id}/requirements | Требования к документам, этап и основание DEMO |
| POST | /applications/{id}/documents | multipart: requirementId, file; PDF/PNG/JPEG до 10 MB |
| GET | /applications/{id}/documents/{versionId} | Закрытое скачивание с проверкой членства |
| POST | /applications/{id}/validate | Проверка данных и комплектности, без кредитного решения |
| GET | /applications/{id}/validation-results | Сохраненные протоколы активной поданной версии |
| POST | /applications/{id}/submit | expectedVersion, confirmed=true; обязательный Idempotency-Key |
| GET | /applications/{id}/status | Статус и история |

Профиль без входа получает секрет `accessToken` **только при создании**. Для каждого дальнейшего
обращения к нему нужен `X-Profile-Token`; в БД хранится только SHA-256. Срок жизни — 7 дней.
Профили вошедших пользователей доступны только создателю. При переносе анонимного профиля в
заявку нужны одновременно Bearer пользователя и X-Profile-Token. UUID не дает доступа.

Поля `answers` (все необязательны для промежуточного сохранения):

```json
{
  "request":{"purpose":"WORKING_CAPITAL","amount":"1000000.00","termMonths":12},
  "registration":{"taxId":"7707083893","name":"Демонстрационный бизнес","borrowerKind":"LLC","registeredOn":"2020-01-01","country":"RU"},
  "business":{"actualStartedOn":"2020-01-01","region":"77","sector":"TRADE","taxRegime":"USN","ipAgeYears":30,"mspRegistry":true,"marketplaceMonths":12,"bankAccountMonths":12},
  "financial":{"revenue":"24000000.00","periodFrom":"2025-10-01","periodTo":"2026-09-30","debtBalance":"0.00","monthlyDebtPayment":"0.00","overdue":false},
  "security":{"collateralReady":false,"guarantorReady":true,"collateralValue":"0.00"},
  "project":{"ownContributionPct":"20.00","purchasePrice":"1250000.00","repaymentSource":"Выручка от основной деятельности"}
}
```

Деньги — десятичные строки, 2 знака после точки, до 17 цифр целой части. Неизвестное поле
отсутствует либо равно null; оно не приравнивается к нулю. Будущие даты и несовместимые
налоговые режимы отклоняются. `fieldSources`, владельцы и банковские статусы устанавливает
сервер. Ручные ответы имеют APPLICANT/MANUAL/DECLARED. Поиск бизнеса не меняет профиль
автоматически. Его синтетические данные при ручном переносе остаются DECLARED.

Доступность: ELIGIBLE / CONDITIONAL / INELIGIBLE; объяснения содержат field, code и message.
Это правила применимости каталога, без ранжирующей модели/скоринга и без одобрения кредита.
При каждом изменении профиля выбор сбрасывается. Пагинация выполняется в SQL; сортировка
разрешена по name, minAmount, annualRatePct в asc/desc с устойчивым дополнительным ключом.
Для списка выдаются карточки без полного policy; детальный endpoint возвращает policy.

Ошибки: application/problem+json: status, title, detail, code, errors. Ошибки полей — 400,
без аутентификации — 401, чужой объект — 404, нет полномочий на запись — 403, устаревшая
версия/состояние/ключ повторного запроса — 409, неполный приемный комплект — 422, большой файл — 413.
Тело SQL-ошибок, пароли, токены и пути хранилища в ответы не попадают.

Отправка в MVP — **демонстрационное подтверждение владельца организации**, а не юридическая
подпись. Согласия субъектов, проверка подписанта и внешние закрытые источники еще требуют
отдельной реализации. OWNER может отправить, EDITOR — готовить, VIEWER — читать.
Снимок создается сервером в одной транзакции, файлы и версия условий фиксируются.
Повтор submit с тем же ключом и параметрами возвращает прежнюю ревизию даже после смены статуса.
Другой запрос с уже использованным ключом — 409. Ключ имеет область пользователя.
Канонизация снимка: рекурсивная сортировка ключей объектов, сохранение порядка массивов,
UTF-8 без пробелов, суммы как строки; SHA-256 не является электронной подписью.

Файл получает RECEIVED, но не VERIFIED. Формат проверяется по сигнатуре, размер и хеш —
сервером. Антивирус пока не подключен: результат UNKNOWN, дальнейшая проверка потребует
сотрудника/сканера; это не кредитный отказ. Для поданной версии протоколы привязаны к ее
снимку, при повторной подаче создается новая версия. Успешная техническая проверка переводит
SUBMITTED → VALIDATING → ENRICHING; недостающие сведения — NEEDS_INFO. До подключения
антивируса загруженные документы блокируют успешную проверку содержимого.

Совместимость springdoc 2.8.x со Spring Boot 3.5.x проверена по [матрице проекта](https://springdoc.org/v2/).
