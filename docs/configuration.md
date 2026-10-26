# Конфигурация и Docker

[Запуск для проверяющих](hackathon-start.md) · [Индекс документации](README.md)

## Подготовка окружения

`setup-demo.ps1` и `setup-demo.sh` создают локальный `.env` из `.env.example`, дополняют отсутствующие параметры и генерируют пустые секреты криптографическим генератором. Непустые значения сохраняются. Файл `.env` исключён из Git.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-demo.ps1
```

```bash
bash scripts/setup-demo.sh
```

После настройки:

```bash
docker compose config --quiet
docker compose up --build --detach --wait --wait-timeout 2400
```

## Переменные

| Переменная | Назначение / значение шаблона |
|---|---|
| `SPRING_PROFILES_ACTIVE` | `demo`: каталог и демо-аккаунты |
| `POSTGRES_DB` | `credit_cabinet` |
| `POSTGRES_ADMIN_PASSWORD` | Пароль администратора PostgreSQL |
| `DB_MIGRATOR_PASSWORD` | Пароль роли Flyway `credit_migrator` |
| `DB_APP_PASSWORD` | Пароль runtime-роли `credit_app` |
| `DEMO_PASSWORD` | Пароль `demo-owner` |
| `DEMO_BANK_PASSWORD` | Пароль `demo-bank` |
| `PGADMIN_DEFAULT_EMAIL` | `admin@example.com` |
| `PGADMIN_DEFAULT_PASSWORD` | Пароль pgAdmin |
| `RECSYS_API_KEY` | Общий серверный ключ Java→FastAPI; setup генерирует 48 hex-символов |
| `MODEL_PATH` | Закреплённый HF-адрес E5 из `.env.example` |
| `RECSYS_MODEL_VARIANT` | `finetuned` |
| `SCORING_ENABLED` | `true` в Compose |
| `SCORING_MODEL_PATH` | `thedauns/sba-scoring-v2` |
| `RECSYS_URL` | `http://fastapi:8000/api/v1/recommendations/rank-java` |
| `SCORING_URL` | `http://fastapi:8000/api/v1/scoring/evaluate` |
| `RECSYS_TIMEOUT_MS` | `10000` |
| `HF_LOCAL_FILES_ONLY` | `false`; `true` читает подготовленный HF-кэш |
| `HF_HUB_DISABLE_XET` | `true`: обычная HTTPS-загрузка |
| `HF_TOKEN` | Токен для выбранного HF-источника при необходимости доступа |
| `RECOMMENDATION_MAX_COSINE_DISTANCE` | Пустое значение выбирает закреплённую policy для варианта модели |
| `SESSION_COOKIE_SECURE` | `false` для локального HTTP, `true` при HTTPS |
| `DEMO_ASSESSMENT_ENABLED` | `false`; переключатель исторической policy 2.1 |

Compose передаёт `RECSYS_API_KEY` как `ML_INTERNAL_API_KEY` в FastAPI и как ключ обоих ML-клиентов Java. При прямом запуске backend отдельно задаётся `SCORING_API_KEY`.

## Порты

| Переменная | Порт хоста |
|---|---:|
| `FRONTEND_PORT` | 3000 |
| `BACKEND_PORT` | 8080 |
| `POSTGRES_PORT` | 5432 |
| `PGADMIN_PORT` | 5050 |
| `FASTAPI_PORT` | 8000 при `compose.dev.yaml` |

Порты публикуются на `127.0.0.1`. Внутри Docker используются имена `frontend`, `backend`, `postgres`, `fastapi`; PostgreSQL слушает 5432, FastAPI — 8000.

Для отладки FastAPI:

```bash
docker compose -f compose.yaml -f compose.dev.yaml up --build --detach --wait --wait-timeout 2400
```

## Источники моделей

E5: `MODEL_PATH` поддерживает HF с immutable revision, локальную папку и S3. [Подробности](../fastapi/MODEL_HANDOFF.md).

SBA: `SCORING_MODEL_PATH` поддерживает закреплённый HF-пакет и локальную папку. [Подробности](../fastapi/SCORING_HF.md).

Папка хоста `fastapi/models` доступна как `/models` и `/scoring-models`. Пример локальных адресов:

```dotenv
MODEL_PATH=/models/e5-credit-finetune-v1/final
SCORING_MODEL_PATH=/scoring-models/custom-scoring
```

HF-кэш хранится в `recsys_model_cache`, `/model-cache` внутри FastAPI. Загрузчики проверяют manifest, контрольные суммы и identity модели до inference.

## Тома и готовность

| Том | Данные |
|---|---|
| `postgres_data` | PostgreSQL и история заявок |
| `documents_data` | Загруженные документы и сформированные договоры |
| `recsys_model_cache` | Пакеты моделей и HF-кэш |
| `pgadmin_data` | Настройки pgAdmin |

PostgreSQL проверяется `pg_isready`, FastAPI — ML-readiness, frontend — запросом `/api/health` через nginx к backend и БД. Начальный интервал загрузки моделей учитывается в healthcheck. `--wait` завершает запуск после готовности сервисов.

## Отдельный экземпляр

Подготовьте отдельный файл конфигурации, задайте свободные порты и используйте отдельное имя проекта:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-demo.ps1 -EnvFile .env.judges
# Edit ports in .env.judges before starting.
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-demo.ps1 -EnvFile .env.judges -ProjectName judges
```

```bash
bash scripts/setup-demo.sh .env.judges
# Edit ports in .env.judges before starting.
bash scripts/start-demo.sh .env.judges judges
```

Для последующих команд сохраняйте ту же пару `--env-file .env.judges --project-name judges`. Данные разных Compose-проектов размещаются в отдельных томах.
