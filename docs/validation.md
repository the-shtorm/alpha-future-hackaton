> 25 октября 2026: [проверка интеграции fast_api](agents/2026-10-25-fast-api-integration-check.md)
> с настоящей дообученной E5, Java и PostgreSQL. Backend: 52 теста;
> FastAPI: 169 тестов и отдельный real-model test; frontend: 11 тестов и сборка.
> Ниже сохранены сведения предыдущих этапов.

## Повторить сквозную проверку Java и E5

После подготовки полной локальной папки модели и настройки `.env`:

```sh
docker compose build backend fastapi
cd fastapi
ML_TEST_IMAGE=alpha-future-fastapi:local ML_TEST_BACKEND_IMAGE=alpha-future-backend:local \
  python3 -m scripts.java_acceptance --model-variant finetuned
```

Скрипту на хосте нужен только Python стандартной библиотеки и Docker Compose.
По умолчанию он использует `fastapi/models/e5-credit-finetune-v1/final`;
для другой папки передайте `ML_TEST_MODEL_PATH=/absolute/path/to/model`.
Модель больше не хранится в Git: подготовка из HF/S3 и экспорт локальной копии
описаны в [MODEL_HANDOFF.md](../fastapi/MODEL_HANDOFF.md).
Он создаёт отдельный проект со случайными локальными портами и одноразовой БД,
проверяет рекомендации, сохранение/восстановление, выбор продукта, черновик заявки,
повторные запросы и запрет устаревшего импорта, затем удаляет только свой стенд.
Для проверки отсутствия рекомендаций можно добавить `--max-cosine-distance 0`;
порог работающего приложения не меняется. Веса монтируются с общей SELinux-меткой `z`.

# Проверки Query/Passage MVP и Preliminary Form 1.1

24 октября 2026 года; ветка `backend-tasks_v2`.
Текущий [отчёт задачи](agents/2026-10-24-query-passage-mvp-frontend.md).
Предыдущий прогон Data Policy 2.1 сохранён в [отдельном отчёте](agents/backend/2026-10-23-data-policy-2-1.md).

## Backend

```sh
mvn -f backend/pom.xml -Dmaven.repo.local=/tmp/alpha-credit-m2 --batch-mode --no-transfer-progress verify javadoc:javadoc
```

35 тестов: BackendIntegrationTest 17, DataPolicyTest 12, EligibilityTest 6.
Проверяются прежние банковские сценарии и новый ручной обмен: полный список кандидатов,
идентификаторы/версии, строгие типы, неизменность применимости, topK, пустой results,
неизменяемость импорта, повтор запроса, устаревшие формы и отсутствие прав.
Точность similarityScore проверяется до 12 дробных знаков, без умножения на 100.

Интеграционная БД — настоящий PostgreSQL 17 в одноразовом Testcontainers; runtime-роль
credit_app. Исходный database_invariants.sql тоже выполняется. Spotless и JavaDoc
(doclint=all, failOnWarnings=true) входят в проверку. Host Java 25, release/target 21;
Docker-образ собирается на Java 21. Проверки не обращаются к модели Recsys.

## Frontend

```sh
npm --prefix frontend run build
npm --prefix frontend test
```

TypeScript + Vite production build. Три проверки сериализации формы: сохранение
false/0/UNKNOWN, удаление возраста ИП при выборе ООО, полный календарный период DEMO.
Prettier проверяет TS/TSX/CSS/JSON/HTML и Compose.

В браузере с отдельной БД и настоящим Spring API проверены вход, форма, ограничения,
загрузка JSON-файла, импорт шести кандидатов, ровно три выделения, показ score без процентов,
сохранение всех условий, выбор продукта и восстановление после перезагрузки.
Ответ для браузерной проверки — явно помеченный TEST_FIXTURE_NOT_MODEL; это не результат
работы настоящей модели и не реализация ранжирования. Внешней команде ничего не отправлялось.
Проверен desktop 1280px без горизонтального переполнения. CSS содержит адаптивные правила;
мобильные устройства отдельно не проверялись.

## Docker и контракт

```sh
docker compose config --quiet
docker compose build frontend backend
```

Оба образа собираются. Frontend дополнительно пересобран после последних UI-исправлений.
nginx-образ проверен отдельным HTTP smoke-test с read-only rootfs, tmpfs, cap_drop ALL,
no-new-privileges: статическая страница возвращает 200. Это отдельно от проверки API
через Vite; совместный запуск всех production-контейнеров не выполнялся.

JSON Schema проверена jsonschema Draft 2020-12: полный ответ и пустой results валидны.
Миграции V1–V9 совпадают с HEAD побайтно; приложенный query_passage_mvp.md сохранён
без изменения. Рабочие контейнеры/тома и пользовательский .env не изменены запуском стенда.
