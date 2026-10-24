# Сохранённые ML-эксперименты

`e5-credit-finetune-v1.json` фиксирует идентичность локальной дообученной модели,
контрольные суммы её файлов и архива, параметры обучения, отдельный порог и результаты
на calibration/development/final test. Веса и окружения в Git не включены.

Сохранённая модель: `fastapi/models/e5-credit-finetune-v1/final/`.
Переносимый архив: `fastapi/models/exports/e5-credit-finetune-v1-116acca8c002.zip`.
Рядом лежит файл `.zip.sha256`; внутри архива — `final/` с manifest,
`training-summary.json` и `selection-policy.json`. Это локальные файлы на машине,
они не появятся после одного только `git clone`.

Проверка архива из PowerShell в `fastapi/`:

```powershell
Get-FileHash models/exports/e5-credit-finetune-v1-116acca8c002.zip -Algorithm SHA256
Get-Content models/exports/e5-credit-finetune-v1-116acca8c002.zip.sha256
```

Обучение из `fastapi/` в отдельном CUDA-окружении Windows/Python 3.11:

```powershell
uv sync --project training --python 3.11
./training/.venv/Scripts/python.exe -m scripts.train_e5 --smoke --output models/e5-credit-smoke-new
./training/.venv/Scripts/python.exe -m scripts.train_e5 --output models/e5-credit-finetune-new
```

Нужны заранее подготовленные базовые веса с revision из `config/model.lock.json`.
Каждому повторному обучению нужен новый output. Оценка сохранённого кандидата:

```powershell
$env:ENVIRONMENT='test'
$env:ML_INTERNAL_API_KEY='local-finetune-evaluation'
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
./.venv/Scripts/python.exe -m scripts.evaluate_finetune
```

Разделение: train 1500, development 180, calibration 180, новый final test 90.
Запросы и familyId между группами не пересекаются; каталог из 15 продуктов общий.
Разметка синтетическая и требует проверки. Финальный тест нельзя использовать для
следующей настройки модели или порога, продолжая считать его независимым.

Статус кандидата — `EXPERIMENT_ONLY`: работающий API продолжает использовать базовую
E5 и её `config/selection-policy.json`. Порог дообученной модели имеет другую шкалу
и хранится вместе с её идентификатором. Подключение кандидата в runtime требует
поддержки его manifest и согласованного порога; подменять revision базовой модели
идентификатором обученного checkpoint нельзя.
