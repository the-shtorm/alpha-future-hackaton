# Загрузка SBA CatBoost из HF или локальной папки

Рабочая версия `sba-scoring-v2` берётся из публичного репозитория
https://huggingface.co/thedauns/sba-scoring-v2. Токен для неё не требуется.
Веса, калибровка, operating threshold и контракт `sba-scoring-1` сохранены.
RecSys/E5 на этой ветке остаётся со своей существующей локальной конфигурацией.

Источник скоринга задаётся одной переменной. В корневом `.env` для Compose:

```dotenv
SCORING_ENABLED=true
SCORING_MODEL_PATH=thedauns/sba-scoring-v2
HF_TOKEN=
HF_LOCAL_FILES_ONLY=false
```

Короткое имя использует immutable HF commit из `config/scoring-hf.lock.json`.
Допустима полная запись:
`hf://thedauns/sba-scoring-v2@5a0049417dae97bdc8a341c89c705d7505563645/model`.
Для другого HF repo требуется явный полный commit SHA. `main` отвергается.
Адрес определяет источник; runtime manifest и все SHA должны соответствовать
`config/scoring-model.lock.json`. Смена адреса не отключает проверку модели.

Локальные альтернативы: `SCORING_MODEL_PATH=C:/models/scoring` или
`SCORING_MODEL_PATH=/srv/models/scoring`. При прямом запуске Python читается
`fastapi/.env`; относительные пути считаются от `fastapi/`. В Docker путь должен
быть контейнерным: папка `fastapi/models/custom-scoring` доступна как
`SCORING_MODEL_PATH=/scoring-models/custom-scoring`. Отдельный HF_TOKEN используется
только при необходимости доступа к private repo. S3 в этом scoring-загрузчике
не реализован; URI других схем отвергаются.

Первый запуск скачивает шесть runtime-файлов в writable кэш. В Linux snapshot
может содержать symlinks; загрузчик создаёт атомарную копию обычных файлов для
строгой проверки manifest. Затем native CatBoost загружается один раз в RAM.
Повторные inference-запросы не скачивают пакет и не создают новый classifier.
После перезапуска модель снова читается из дискового кэша.

В Compose настроен постоянный `recsys_model_cache:/model-cache`; не удаляйте его,
если хотите сохранить скачанные файлы. HF_HOME и HF_XET_CACHE также направлены
в этот writable volume. `HF_LOCAL_FILES_ONLY=true` допускает только готовый кэш.
Не задавайте внешний `HF_HUB_OFFLINE=1` перед первой сетевой загрузкой.

Проверка пакета без E5, переобучения и рабочего API-ключа, из `fastapi/`:

```powershell
uv sync --frozen --python 3.11
uv run --frozen python -m scripts.prepare_scoring_model --smoke
uv run --frozen python -m scripts.prepare_scoring_model --local-files-only --smoke
```

Для HTTP-сервиса по-прежнему требуются E5 и общий внутренний ключ Java/FastAPI.
Scoring endpoints защищены внутренним Bearer. `/api/v1/scoring/ready` показывает
готовность скоринга; общая readiness RecSys от неё независима. При сбое
скачивания/manifest скоринг остаётся 503, автоматического fallback на v1 нет.

```powershell
docker compose up -d --build --no-deps fastapi
```

Пакеты v1/v2 больше не отслеживаются в Git и удалены из `fastapi/models/sba-*`.
Перед миграцией сохранена игнорируемая локальная резервная копия; веса v2 также
проверены на HF по исходному manifest SHA. История Git не переписывалась.
E5 LFS rules остаются в этой ветке: изменение касается только scoring-пакетов.

Полная проверка нативного пакета opt-in: после подготовки кэша задайте
`RUN_SCORING_INTEGRATION=1` и запустите `tests/integration/test_scoring_v2_package.py`.
Историческая проверка v1 требует отдельной `SCORING_V1_MODEL_PATH`; v1 не
скачивается автоматически. Обычные unit-тесты используют маленькие fitted fixtures.

Изолированная проверка Java/БД/frontend и совместной работы со штатной E5:
после сборки образов, указанных в `scripts.scoring_stack_acceptance`, запустите
`python -m scripts.scoring_stack_acceptance --source-smoke --output reports/scoring-source.json`.
Она проверяет два сценария: отказ с настоящей оценкой v2 и запрос недостающих данных,
а также scoring HTTP под нагрузкой E5. Это проверка интеграции источника модели.
Запуск без `--source-smoke` проверяет все четыре исхода, включая подписание и выдачу
для APPROVED/COUNTEROFFERED. Fixture одобрения обновлена для v2: существующий P07,
500000 RUB, 60 месяцев, обеспечение и собственный взнос 20%; остальные исходы
проверяются на P01. Все четыре исхода прошли настоящий HTTP-прогон. Это синтетические
проверки ветвей интеграции, не независимая оценка ML-качества. Модель и Java policy
для получения ожидаемых исходов не менялись.

Модель остаётся демонстрационной US SBA → RU. Известные метрики/ограничения,
OOD-предупреждения и Java risk/PTI-правила этой миграцией не пересматриваются.
