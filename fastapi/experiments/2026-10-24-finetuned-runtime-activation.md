# Подключение дообученной E5 и проверка совместимости

Дата: 2026-10-24, ветка `fast_api`. Запрос: подключить дообученную E5 и после
подключения повторно проверить совместимость всей цепочки. По прежнему указанию
пользователя `docs/` не редактировалась.

## Фактическое состояние

Основной локальный FastAPI-контейнер использует `local/e5-credit-finetune-v1`.
Полный revision в `/api/v1/model-info` и metadata ответа:
`116acca8c00237091e511ea6e96a2959ad1345d9439b8c5a9c7fc2c29b9012e8`.
Это SHA-256 артефакта, а не Git SHA исходной E5.

Порог cosine distance: `0.4941788911819458` (similarity не ниже
`0.5058211088180542`). Порог ранее выбран на отдельной calibration; после
подключения он не подстраивался. Полный ranking всех кандидатов сохраняется;
рекомендации — непрерывный префикс из 0…topK позиций, максимум 3.

Реальные веса, manifest и переносимый ZIP сохранились без изменений, в Git не
добавлялись. Обучение повторно не запускалось. Вычисления сервиса идут на CPU
float32, batch 4, threads 2/interop 1, размерность 384, предел текста 512 токенов.
Качество по-прежнему подтверждено только на синтетических предложенных метках
для известного каталога из 15 продуктов.

## Изменения

- Runtime поддерживает два явно выбранных варианта: `finetuned` по умолчанию и
  `base` для исходной модели. Для каждого используются собственные lock и policy.
- `config/finetuned-model.lock.json` закрепляет идентификатор и полный SHA весов,
  `finetuned-selection-policy.json` — согласованный порог и версии шаблонов.
- При startup проверяются набор файлов, все SHA-256, artifact identity, исходная
  модель/revision, размерность и maxSeqLength. Несовпадение останавливает startup.
  Автоматической подмены на базовую модель нет.
- Проверка fine-tuned manifest вынесена из вспомогательного training-кода в runtime;
  training/evaluation используют ту же проверку. Хеширование весов потоковое.
- Compose монтирует сохранённый checkpoint read-only в `/models/active`.
  Identity/revision берутся из lock, старый MODEL_REVISION базовой модели больше
  не передаётся в ML-контейнер.
- Подготовка базовых весов, исходная калибровка и baseline в экспериментах явно
  выбирают `model_variant=base`, чтобы не смешивать шкалы и модели.
- Java acceptance умеет `--model-variant finetuned`. CI по умолчанию проверяет
  базовые веса: дообученные локальные файлы не опубликованы и отсутствуют в Git.
- Запись эксперимента и инструкция в `experiments/` обновлены. Исторический
  отчёт предыдущей проверки оставлен как снимок прежнего состояния.

## Обновление основного стека

В реально запущенном Java JAR обнаружено старое требование «ровно topK».
Поэтому обновлены два контейнера: FastAPI и backend с уже проверенным адаптером
0…topK. Docker image backend совпадает с образом, использованным в acceptance.
PostgreSQL, frontend, pgAdmin и посторонние контейнеры не пересоздавались;
сравнены их container ID до и после. Том БД не удалялся и не пересоздавался.

В старом ML-контейнере внутренний ключ отсутствовал. Создан случайный ключ,
сохранён только в локальном игнорируемом `.env` и передан обоим сервисам.
Совпадение ключей и адрес gateway проверены без вывода секретов. Первоначальная
попытка Compose остановилась на отсутствии ключа до изменения контейнеров;
после настройки оба контейнера получили healthy.

## Проверки после подключения

| Проверка | Фактический результат |
|---|---|
| Runtime model-info | local/e5-credit-finetune-v1, полный SHA и новый порог совпадают с lock/policy |
| Runtime health/live, ready, alias | HTTP 200 |
| Runtime core rank и Java rank | HTTP 200, DTO валидны, все кандидаты, не более 3 рекомендаций |
| Java health, gateway, общий ключ | успешно |
| Java → fine-tuned E5 → Java, отдельный временный стек после подключения | passed=true |
| conditional | READY: 4 кандидата / 2 рекомендации |
| unknown_context | READY: 4 кандидата / 3 рекомендации |
| logistics | READY: 4 кандидата / 2 рекомендации |
| empty | EMPTY: 0 кандидатов / 0 рекомендаций |
| FastAPI Windows, обе реальные модели | 169 passed, app coverage 100% |
| FastAPI offline Linux, обе реальные модели | 169 passed, 2 CPU / limit 2 GiB |
| Java mvn verify с PostgreSQL Testcontainers | 51 tests, 0 failures/errors/skips, BUILD SUCCESS |
| Frontend TypeScript + Vite, Node 22 Docker | сборка успешна |
| Frontend tests, Node 22 Docker | 7 passed |
| Работающий frontend | HTTP 200, text/html |
| OpenAPI и JSON Schema | совпадение/валидность проверены тестами; форма ответа не менялась |
| Ruff / format --check | успешно, 65 файлов |

Windows-проверка обеих моделей выполнена перед переключением; после переключения
полный набор повторён в offline Linux. Backend verify и отдельный Java acceptance
повторены после переключения. UI проверен сборкой, тестами и HTTP-доступностью;
отдельный интерактивный браузерный прогон не выполнялся. Локальная попытка сборки
frontend не нашла tsc, так как node_modules отсутствовал; проверка завершена
успешно в Docker с npm ci из lock-файла, исходники frontend не менялись.

Основные команды: `python -m pytest` с `RUN_REAL_MODEL_TESTS=1` и
`RUN_FINETUNED_MODEL_TESTS=1`; `mvn verify`; `python -m scripts.java_acceptance
--model-variant finetuned`; Docker build frontend и `npm test` внутри Node 22.
Runtime обновлён через `docker compose up -d --no-deps --no-build --wait fastapi backend`
после сборки/проверки образов.

Локальные сырые результаты: `work/ml-acceptance/active-finetuned-runtime.json`,
`finetuned-post-activation-java-e2e.json`, `finetuned-linux-runtime-tests.log`,
`finetuned-backend-verify.log`; Windows JUnit:
`fastapi/reports/finetuned-runtime-tests.xml`.

Новые подборы используют дообученную модель. Ранее сохранённые Java результаты
не пересчитываются: для новой оценки нужно создать новый подбор, metadata
старого ответа остаётся исторической. Файлы `docs/`, `draft.ipynb`, основной и
CUDA lock-файлы зависимостей не менялись. Внешняя публикация не выполнялась.
