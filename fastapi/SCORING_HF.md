# Загрузка и проверка SBA CatBoost

[Документация проекта](../docs/README.md) · [Политика решения](../docs/credit-scoring.md) · [Обучение](scoring_training/README.md)

## Штатный Compose

Настройки задаются в корневом `.env`:

```dotenv
SCORING_ENABLED=true
SCORING_MODEL_PATH=thedauns/sba-scoring-v2
HF_LOCAL_FILES_ONLY=false
HF_TOKEN=
```

Пакет опубликован в `thedauns/sba-scoring-v2` и доступен для анонимной загрузки.
Короткое имя разрешается через `config/scoring-hf.lock.json` в закреплённый commit:

```dotenv
SCORING_MODEL_PATH=hf://thedauns/sba-scoring-v2@5a0049417dae97bdc8a341c89c705d7505563645/model
```

Полный HF-адрес должен содержать immutable commit SHA. Runtime manifest и SHA
файлов сверяются с `config/scoring-model.lock.json`: версия `sba-scoring-v2`,
manifest SHA-256 `5d5498e8d3339ffbbce3d5f117f52692cee9986067a3bf6df8524c5e4c8c53ac`.
Модель, калибровка и operating threshold проверяются как единый пакет.

При первом запуске загружаются шесть runtime-файлов. Кэш хранится в
`recsys_model_cache` (`/model-cache`); загрузчик создаёт проверенную обычную
папку из HF snapshot. Native CatBoost загружается один раз в RAM.
Для каждого запроса используется уже загруженный classifier.

## Проверка готового сервиса

Из корня после запуска:

```sh
docker compose exec -T fastapi python -m scripts.prepare_scoring_model --smoke
```

Результат содержит `verified=true`, модель, калибровку, порог и контрольный прогноз.
Для штатного примера вероятность `0.2525274156209339`, score `75`.
Внутренние endpoints защищены Bearer-ключом из `RECSYS_API_KEY`:

| Endpoint | Назначение |
|---|---|
| `GET /api/v1/scoring/ready` | Готовность SBA |
| `GET /api/v1/scoring/model-info` | Модель, признаки, калибровка и runtime |
| `POST /api/v1/scoring/evaluate` | Inference по `sba-scoring-1` |

`/health/ready` проверяет готовность рекомендательной E5; у скоринга есть
собственная readiness. Полный клиентский сценарий проверяет обе модели.

## Локальная папка и прямой Python-запуск

Источник поддерживает HF и локальную папку. В Docker каталог
`fastapi/models/custom-scoring` доступен как `/scoring-models/custom-scoring`:

```dotenv
SCORING_MODEL_PATH=/scoring-models/custom-scoring
```

При прямом запуске используется `fastapi/.env`; относительные пути считаются
от `fastapi/`. Установите Python 3.11 и выполните из `fastapi/`:

```sh
uv sync --frozen
uv run --frozen python -m scripts.prepare_scoring_model --smoke
uv run --frozen python -m scripts.prepare_scoring_model --local-files-only --smoke
```

`--model-path` и `--cache-dir` позволяют явно проверить другой путь и кэш.
Локальный пакет проходит ту же проверку manifest и SHA. Для самого HTTP-сервиса
также нужны настроенная E5 и внутренний ключ Java/FastAPI.

## Интеграционные проверки

`RUN_SCORING_INTEGRATION=1` включает `tests/integration/test_scoring_v2_package.py`
после подготовки кэша. Обычные unit-тесты используют маленькие fitted fixtures.

Из `fastapi/` скрипт `python -m scripts.scoring_stack_acceptance --help`
описывает изолированный Docker-прогон с реальными пакетами. После подготовки E5
и сборки указанных в скрипте образов запуск без `--source-smoke` проверяет
четыре исхода и положительные пути до учебной выдачи; `--cookie-auth`
проверяет их через nginx с отдельными owner/bank cookie jars и CSRF.
`ML_TEST_MODEL_PATH` задаёт абсолютный host-путь к E5 для тестового bind mount.
Штатный сервис использует `MODEL_PATH`.

Схемы, версии, метрики и происхождение SBA описаны в
[credit-scoring.md](../docs/credit-scoring.md) и
[индексе исследований](experiments/README.md). Веса, кэши и исходные CSV
хранятся вне Git; для запуска используется готовый HF-пакет.
