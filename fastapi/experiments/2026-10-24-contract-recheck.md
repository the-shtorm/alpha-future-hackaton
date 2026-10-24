# Повторная проверка контрактов и сохранение модели

Запрос: повторно проверить контракты, сохранить дообученную модель и закоммитить
накопленные изменения в ветке `fast_api`. Пользователь запретил менять `docs/`,
поэтому отчёт находится в `fastapi/experiments/`.

## Проверенные контракты

- Сохранённый OpenAPI побайтово не сравнивался: проверено равенство JSON-структуры
  с `create_app().openapi()`. Различий нет.
- Все три JSON Schema проходят `check_schema`. Схема ответа Java в
  `fastapi/contracts/java-rank-response.schema.json` совпадает с
  `docs/contracts/ranking-response.schema.json`.
- Проверены поля DTO, enum, nullable-значения, UUID/version, неизменность
  eligibilityStatus и полного pendingConditions, auth, ошибки и лимиты.
- Согласованный смысл topK: 0…topK рекомендаций (не более 3), полный список
  кандидатов возвращается всегда. Java принимает только непрерывный префикс
  рекомендаций и отвергает пропуски/избыточные флаги.
- Реальный Java HTTP gateway → CPU E5 → неизменяемый импорт Java проверен
  в отдельном временном Docker Compose project. Сценарии conditional,
  unknown_context и logistics имеют READY, по 4 кандидата; empty имеет EMPTY
  и 0 кандидатов. Проверены повторный импорт, retry и отклонение устаревшей формы.
- Frontend использует существующие boolean isRecommended и numeric
  similarityScore; изменения JSON-формы для него не потребовались. Отдельная
  браузерная проверка/frontend-сборка в этой задаче не запускались.

Добавлены регрессионные тесты совпадения OpenAPI, валидности JSON Schema,
полноты Java response DTO и ссылок SHA-256 калибровочной политики.

В `docs/ranking-exchange.md` остаётся устаревшее описание «ровно top-3» и ручного
обмена. Код и тесты соответствуют последующему запросу пользователя о 0–3
рекомендациях и автоматическому обмену. Текстовые документы не редактировались.

## Воспроизводимость Git

При проверке Git index обнаружено, что автоматическая нормализация CRLF → LF
меняет SHA-256 замороженных JSON-данных. Для `fastapi/evaluation/*.json` и
`fastapi/config/selection-policy.json` отключено преобразование окончаний строк.
Существующие байты и SHA, использованные при обучении, сохранены; модели и
пороги не пересчитывались. Сверены байты и SHA всех пяти inputSha256 из записи
эксперимента с Git index, а также ссылки калибровочной политики на каталог и
calibration. Проверка Linux запускалась на копии файлов из Git index, не на
случайной версии рабочего дерева.

## Сохранённая модель

- Модель: `fastapi/models/e5-credit-finetune-v1/final/`.
- Переносимый локальный архив:
  `fastapi/models/exports/e5-credit-finetune-v1-116acca8c002.zip`, 487771755 байт.
- SHA-256 архива:
  `7d4a7d1726c98af0d61edad92149370f72946cf397897dbdc6c75cb964f746db`.
- Artifact SHA-256:
  `116acca8c00237091e511ea6e96a2959ad1345d9439b8c5a9c7fc2c29b9012e8`.
- Проверены все исходные файлы по manifest и CRC всех записей ZIP.
- В Git сохранена запись `e5-credit-finetune-v1.json`: manifest, контрольные суммы,
  параметры, метрики, экспериментальный порог и результаты CPU benchmark.
- Веса, ZIP, окружения и секреты остаются вне Git. На Hub ничего не публиковалось.
- Работающий сервис не переключён на экспериментальный checkpoint. Базовые веса
  и production-порог не изменены. Разметка синтетическая; каталог общий для всех
  частей оценки, качество на реальных клиентах не подтверждено.

## Фактические проверки

| Проверка | Результат |
|---|---|
| Windows pytest, RUN_REAL_MODEL_TESTS=1 | 158 passed, app coverage 100% |
| Linux Docker, snapshot Git index, network none, real weights | 158 passed |
| Java mvn verify, PostgreSQL Testcontainers | 51 tests, 0 failures/errors/skips; BUILD SUCCESS |
| Spotless | все 30 Java-файлов проходят |
| Ruff check / format --check | успешно, 64 Python-файла |
| Docker build FastAPI и backend | успешно |
| Изолированный Java → ML → Java acceptance | passed=true, 4 сценария |
| Основной и CUDA uv.lock, lock --check --offline | успешно |
| git diff --cached --check | успешно |
| docs/ и основной fastapi/uv.lock | без изменений |

Первый `uv lock --check` не смог записать служебный sandbox-кэш. Повторный запуск
с `UV_CACHE_DIR` внутри workspace прошёл для обоих lock-файлов. Предупреждения
pytest касаются переименования метода Sentence Transformers и смены HTTP-клиента
Starlette; ошибок тестов нет.

Проверки выполнялись командами `python -m pytest`, `mvn verify`,
`python -m scripts.java_acceptance`, `uv lock --check --offline`. Локальные сырые
логи и JSON: `work/ml-acceptance/backend-contract-recheck.log`,
`contract-recheck-java-e2e.json`, `linux-staged-contract-recheck.log`.

В коммит включены накопленные изменения порогового выбора, Java-совместимости,
синтетические splits, эксперименты reranker/дообучения, отдельный CUDA lock,
тесты и запись модели. Изменений структуры БД или миграций нет. Пользовательский
Docker-стек не перезапускался; временные тестовые ресурсы удалены скриптами.
