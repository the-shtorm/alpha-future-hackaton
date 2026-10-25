# Сохранённые ML-эксперименты

`e5-credit-finetune-v1.json` фиксирует идентичность локальной дообученной модели,
контрольные суммы её файлов и архива, параметры обучения, отдельный порог и результаты
на calibration/development/final test. Модель и полный пакет хранятся на Hugging
Face; локальные веса, tokenizer, manifest и окружения больше не отслеживаются Git.

**Передача и запуск модели: [MODEL_HANDOFF.md](../MODEL_HANDOFF.md).**
Выберите MODEL_PATH (локальный путь, hf:// или s3://) в fastapi/.env, затем выполните из fastapi/
`uv run --frozen python -m scripts.verify_model --smoke`.

Сохранённая модель: `fastapi/models/e5-credit-finetune-v1/final/`.
Переносимый архив: `fastapi/models/exports/e5-credit-finetune-v1-116acca8c002.zip`.
Рядом лежит файл `.zip.sha256`; внутри архива — `final/` с manifest,
`training-summary.json` и исторический `selection-policy.json`. ZIP остаётся
локальной резервной копией. Готовый пакет передаётся через приватный HF-репозиторий
thedauns/e5-credit-finetune-v1, GitHub хранит только код и небольшие ресурсы.

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
Каждому повторному обучению нужен новый output. Историческая оценка с повторной
калибровкой F0.5:

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

Текущая политика выбрана по максимуму micro F1 на calibration: similarity
не ниже `0.47622181475162506`, то есть distance не выше `0.5237781852483749`.
Исторические метрики и порог F0.5 в записи обучения относятся к первоначальному
эксперименту; актуальный runtime-порог задаёт файл политики.

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

Для этого образ должен быть собран из текущего кода и локальная модель подготовлена
из HF-пакета. Ручные CI model-package/real-java скачивают pinned HF revision и
требуют MODEL_PATH в Variables и соответствующий токен в Secrets.
Для полного локального pytest с обоими checkpoint задаются
RUN_REAL_MODEL_TESTS=1 и RUN_FINETUNED_MODEL_TESTS=1.

Текущий F1-порог проверяется без перенастройки через
`uv run --frozen python -m scripts.evaluate_active_model`; дополнительные 15
диагностических примеров — через `--dataset evaluation/diagnostic-15.json`.

Новые подборы используют текущую модель. Ранее сохранённые результаты Java
неизменяемы и сохраняют собственную metadata; для пересчёта нужен новый подбор.
