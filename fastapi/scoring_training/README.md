# SBA: отдельное CPU-обучение и воспроизводимость

Основная модель теперь **sba-scoring-v2**, выбранная №5 (`mixed-v1-0051`):
[пакет и точные метрики](../models/sba-scoring-v2/README.md),
[эксплуатация и откат](../../docs/credit-scoring.md). На исторической FY2023:
recall70.08%, precision58.96%, F1 64.04% при фиксированном t=0.167204479067272.
Полная кампания завершена:1489 записей, включая72 mixed и200 recent holdout.
Последняя цель85/55 и допустимые84/53 не достигнуты; выбран существенный прирост
относительно сохранённого фаворита. Это не свежий независимый тест.

Исходный [план90/60](../../docs/scoring-retraining-recall90-precision60-plan.md)
и матрица `config/recall90-precision60-plan.json` сохранены как история. Доступен
`business_thresholds.business_operating_points(y, p)`: полный перебор уникальных
порогов с максимумом F1 при обоих ограничениях. Все три метрики берутся при одном
пороге; при отсутствии решения `optimal=null`, `status=infeasible` и две полные
граничные альтернативы. Порог выбирается на отдельной development-когорте.

Первоначальный pipeline V1: подготовка CSV, 32 эксперимента, выбор модели, диагностика срока,
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

## Перебор порогов с приоритетом recall

Для текущего замороженного пакета доступен отдельный offline-эксперимент:

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
