# SBA: отдельное CPU-обучение и воспроизводимость

Рабочая модель приложения — **sba-scoring-v2**, кандидат `mixed-v1-0051`.
Для inference пакет загружается из закреплённого HF revision; повторное обучение
не требуется. [Загрузка](../SCORING_HF.md), [банковская политика](../../docs/credit-scoring.md),
[результаты кампании](../experiments/sba-scoring-campaign-v1/README.md).
На сохранённой FY2023: recall 70.08%, precision 58.96%, F1 64.04% при
`t=0.167204479067272`. Кампания содержит 1489 записей, включая 72 mixed и
200 recent holdout. Метрики относятся к сохранённой ретроспективной оценке.

Ниже описан воспроизводимый первоначальный CPU pipeline V1 и отдельный поиск
порогов. Кампания V2 и выбор кандидата документированы в индексе экспериментов.
Исходный [план 90/60](../../docs/scoring-retraining-recall90-precision60-plan.md)
сохранён как история исследования. `business_thresholds.business_operating_points`
перебирает уникальные пороги с обоими ограничениями и сохраняет результат поиска.

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

Сырые CSV, подготовленные представления, окружения и пробные модели в `runs/`
игнорируются Git. Передаётся только выбранный inference-пакет и обезличенная
документация эксперимента. В тестах используются маленькие искусственные CSV и
настоящие fitted-модели для проверки сериализации; это не SBA-метрики.

## Перебор порогов с приоритетом recall

Для исторического замороженного пакета V1 доступен отдельный offline-эксперимент:

```sh
scoring_training/.venv/bin/python -m scoring_training.threshold_search \
  --prepared ../data/scoring/prepared/sba-v1 \
  --package models/sba-scoring-v1 \
  --output scoring_training/runs/sba-recall-thresholds-new \
  --recommended-recall 0.95
```

Нужен новый каталог результата. Перебираются все уникальные калиброванные вероятности
FY2017 и границы 0/1; положительный прогноз означает `p >= threshold`, класс 1 —
списание. Одинаковые вероятности не разделяются. Сравниваются максимум F1, максимум
F2, наибольший recall в пределах 0.01 от лучшего F1, а также максимумы F1 при
recall >=90/95/98%. При равном целевом F-score выбирается больший recall.
Рекомендация по умолчанию — максимум F1 при recall >=95% на FY2017; это явно
принятое допущение эксперимента, а не согласованный бизнес-лимит.

`selection.json` записывается до чтения test/transfer, затем фиксированные пороги
оцениваются на FY2018–2019 и FY2020–2026, по годам и в backend-достижимых категориях.
Сохраняются F1/F2, precision/recall, TP/FP/FN/TN, доля флагов и FPR.
`comparison.csv` содержит выбранные политики, `development-exact-curve.csv` — полный
перебор, `development-grid.csv` — компактную сетку для графика,
`threshold-tradeoffs.png` — сравнение метрик. Полный перебор остаётся в игнорируемом
`runs/`; компактные результаты и выводы публикуются в `../experiments/`.

FY2017 уже обучал калибратор: его метрики подбора предварительные. Поздние когорты
оценивались исторически; это существующий ретроспективный benchmark. Новые пороги
не подбираются на них и не гарантируют будущий recall. Эксперимент не изменяет
пакет, API или многосоставную Java-политику выдачи/альтернативного предложения.
