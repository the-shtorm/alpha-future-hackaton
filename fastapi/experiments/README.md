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

Работающий API и Compose по умолчанию используют дообученную E5:
`MODEL_VARIANT=finetuned`, `config/finetuned-model.lock.json` и
`config/finetuned-selection-policy.json`. В model-info и metadata возвращается
`local/e5-credit-finetune-v1`, а revision — полный SHA-256 артефакта, отличный от
Git revision базовой E5. Порог дообученной модели имеет другую шкалу и привязан
к её идентификатору. Исходный архив checkpoint не изменяется.

Compose монтирует `models/e5-credit-finetune-v1/final` read-only. Для явного
возврата на базовую модель нужно согласованно задать в корневом `.env`:

```dotenv
RECSYS_MODEL_VARIANT=base
RECSYS_MODEL_PATH=./fastapi/models/multilingual-e5-small
```

При запуске Python напрямую используется `MODEL_VARIANT=base`; путь к базовой
модели выбирается автоматически, если `MODEL_LOCAL_PATH` не задан. Несовпадение
identity/revision/manifest прекращает startup, автоматической подмены нет.
Для каждого варианта загружается собственный калибровочный порог. Явный
`RECOMMENDATION_MAX_COSINE_DISTANCE` переопределяет его.

Проверка всей Java-цепочки с сохранённым checkpoint в отдельном временном стеке:

```powershell
./.venv/Scripts/python.exe -m scripts.java_acceptance --model-variant finetuned
```

Для этого образ должен быть собран из текущего кода. CI использует `base`, потому
что локальные дообученные веса не опубликованы и не хранятся в Git. Для полного
локального pytest с обоими checkpoint задаются `RUN_REAL_MODEL_TESTS=1` и
`RUN_FINETUNED_MODEL_TESTS=1`.

Новые подборы используют текущую модель. Ранее сохранённые результаты Java
неизменяемы и сохраняют собственную metadata; для пересчёта нужен новый подбор.
