# SBA: отдельное CPU-обучение и воспроизводимость

Реализованы подготовка CSV, 32 эксперимента, выбор модели, диагностика срока,
переобучение, отдельная sigmoid-калибровка FY2017, независимая оценка и проверяемый
inference-пакет. Результат `sba-scoring-v1` находится в `../models/sba-scoring-v1/`.
Параметры и результаты всех кандидатов: `../experiments/sba-scoring-v1.json`.
Это демонстрационная оценка списания SBA, не подтверждённая российская банковская PD.

Все команды ниже выполняются из `fastapi/`, Python 3.11:

```sh
uv sync --project scoring_training --frozen
scoring_training/.venv/bin/python -m pytest -c scoring_training/pyproject.toml scoring_training/tests
scoring_training/.venv/bin/ruff check app/scoring scoring_training
scoring_training/.venv/bin/python -m scoring_training.export_contracts
```

CPU-окружение и его lock независимы от `training/` с CUDA для E5. E5 checkpoint,
его идентичность и пороги не меняются. Общие признаки находятся в `app/scoring/`;
HTTP scoring использует те же правила, что CSV-подготовка. Категории остаются
строками, процентные пункты не делятся на 100, сумма уже выражена в USD.

## Подготовка

Неизменённый CSV пользователя хранится в `data/scoring/raw/` от корня репозитория.
Хеш, точный заголовок, классы, даты и временные когорты закреплены в
`config/dataset.lock.json`. Новая версия CSV требует нового lock с новой версией;
подготовка не разрешает автоматически продолжить эксперимент после изменения данных.

```sh
scoring_training/.venv/bin/python -m scoring_training.data \
  --csv '../data/scoring/raw/sba_dataset(2010-2026).csv' \
  --output ../data/scoring/prepared/sba-v1
```

Каталог назначения должен быть новым. Проверяются хеш до/после чтения, заголовок,
коды, цель, четыре календарные даты, FY и размеры когорт. Исходник не меняется;
результат публикуется после всех проверок. Пять CSV, `split-index.csv` и manifest
сохраняют индексы строк от нуля. В X всегда входят ровно девять имён из
`app.scoring.features.FEATURES`; даты исходов и метаданные туда не попадают.
Повторы признаков учитываются, строки не удаляются, уникальность заёмщика не доказана.

## Подбор, заморозка и оценка

Для повторного запуска использовать **новые** пути эксперимента и пакета:

```sh
scoring_training/.venv/bin/python -m scoring_training.train tune \
  --prepared ../data/scoring/prepared/sba-v1 --experiment scoring_training/runs/sba-new
scoring_training/.venv/bin/python -m scoring_training.train freeze \
  --prepared ../data/scoring/prepared/sba-v1 --experiment scoring_training/runs/sba-new \
  --package models/sba-scoring-new --version sba-scoring-new
scoring_training/.venv/bin/python -m scoring_training.train evaluate \
  --prepared ../data/scoring/prepared/sba-v1 --experiment scoring_training/runs/sba-new \
  --package models/sba-scoring-new
```

`tune` читает только train/validation: 8 LogisticRegression + 24 CatBoost, seed 42,
четыре CPU-потока, последовательные опыты. LR выбирается, если её Log Loss в пределах
0,5% от лучшего. Сходимость обязательна. CatBoost использует штатные категории,
1500 итераций и early stopping 100; сохраняется найденное число деревьев.

`freeze` переобучает выбранную конфигурацию на FY2010–2016 с фиксированным числом
итераций и обучает sigmoid только на FY2017. Записывает веса, domain, калибратор,
provenance и `frozen-before-test.json`. `evaluate` проверяет эту заморозку до чтения
FY2018–2019 и FY2020–2026. Итоговые результаты не используются для настройки.
Веса и калибратор при оценке не меняются; в пакет добавляются метрики и технические
release gates. Повторная оценка поверх изменённого manifest блокируется.

Оценка содержит ROC-AUC, Average Precision, Log Loss, Brier, calibration bins с
количествами, пороги 0.15/0.35, годовые/отраслевые/категориальные срезы и отдельно
категории, достижимые из backend. Диаграмма: `calibration.png` выбранного пакета.

Важное ограничение v1: на validation ROC-AUC снизился с 0.970 до 0.681 без срока.
Это сильная чувствительность; историческая доступность изменяемого срока не
подтверждена. Прямые outcome-поля исключены, но причинная и банковская пригодность
не доказана. Runtime всегда возвращает `TERM_HISTORY_UNCONFIRMED` и `SBA_US_TO_RU_DEMO`.

Сырые CSV, подготовленные представления, окружения и пробные модели в `runs/`
игнорируются Git. Передаётся только выбранный inference-пакет и обезличенная
документация эксперимента. В тестах используются маленькие искусственные CSV и
настоящие fitted-модели для проверки сериализации; это не SBA-метрики.
