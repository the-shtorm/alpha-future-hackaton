# SBA: отдельное CPU-окружение

Статус: реализованы контракты, общие признаки и подготовка CSV. Обучение,
калибровка, inference-пакет и Java-интеграция — следующие этапы
[плана](../../docs/credit-scoring-implementation-plan.md).
Обученной модели и метрик реального SBA-датасета пока нет.

Все команды ниже выполняются из `fastapi/`, Python 3.11:

```sh
uv sync --project scoring_training --frozen
scoring_training/.venv/bin/python -m pytest -c scoring_training/pyproject.toml scoring_training/tests
scoring_training/.venv/bin/ruff check app/scoring scoring_training
scoring_training/.venv/bin/python -m scoring_training.export_contracts
```

`uv.lock` закрепляет CPU-зависимости обучения, независимо от `training/` с CUDA
для E5. Существующий runtime E5 не меняется. Новые схемы находятся в
`contracts/scoring-{request,response}.schema.json`; HTTP-обработчик ещё не подключён.

## Исходные данные и подготовка

Папка для неизменённого CSV пользователя: `data/scoring/raw/` от корня репозитория.
Ожидаемая версия и SHA-256 взяты из согласованного плана и закреплены в
`config/dataset.lock.json`. Подготовка по умолчанию блокируется до получения CSV:
необходимо проверить его хеш, зафиксировать **точный** заголовок в `columns`,
сопоставить четыре даты в `dateColumns`, затем установить `schemaStatus=verified`.
Каждая дата задаётся тройкой имён колонок в порядке год, месяц, день; роли:
`approval`, `asOf`, `paidInFull`, `chargeOff`.

После проверки схемы:

```sh
scoring_training/.venv/bin/python -m scoring_training.data \
  --csv '../data/scoring/raw/sba_dataset(2010-2026).csv' \
  --output ../data/scoring/prepared/sba-v1
```

Выходной каталог должен быть новым. Подготовка проверяет исходный хеш до и
после чтения; заголовок, девять признаков, коды, цель, даты и американский
финансовый год; количество строк, классы и каждую когорту. Исходник не меняется.
Частично подготовленные результаты при ошибке не публикуются.

Результаты: пять CSV по временным частям, `split-index.csv` с нумерацией исходных
строк от нуля и `manifest.json` с контрольными суммами, происхождением данных и
ограничениями. Даты исходов остаются только в исходном CSV; в X всегда входят
только имена из `app.scoring.features.FEATURES`. Совпадения признаков учитываются,
строки автоматически не удаляются. Это не проверка уникальности заёмщика.

Данные, подготовленные представления, локальные окружения и `runs/` исключены
из Git. Тесты используют маленькие искусственные CSV; они не заменяют проверку
реального файла, обучение и измерение качества.
