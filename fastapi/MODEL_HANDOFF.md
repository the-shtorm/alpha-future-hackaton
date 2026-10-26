# Передача и запуск дообученной E5

[Документация проекта](../docs/README.md) · [Запуск Docker](../docs/hackathon-start.md)

## Хранение

HF-репозиторий: `thedauns/e5-credit-finetune-v1`.
В HF `model/` содержит 10 неизменённых inference-файлов; `service/` — код,
словарь, контракты, примеры, синтетические данные, параметры и lock-файлы обучения.
`package-manifest.json` фиксирует SHA переданных файлов. Секреты, окружения, кэши
и промежуточные training checkpoints не включаются. GitHub хранит код и небольшие
ресурсы. Локальные веса в models/e5-credit-finetune-v1/final сохранены вне Git.

## Одна переменная MODEL_PATH

В штатном Docker Compose MODEL_PATH задаётся в корневом `.env`. При прямом
запуске Python источник определяется MODEL_PATH в fastapi/.env или в переменных
процесса. Переменные процесса имеют приоритет. Примеры альтернативных значений:

```dotenv
# HF, immutable revision внутри того же значения:
MODEL_PATH=hf://thedauns/e5-credit-finetune-v1@e93f86ce54f0a6d2b3da24dac803e50ee92bbb2b/model
# Для этого известного репозитория допустима короткая запись:
# MODEL_PATH=thedauns/e5-credit-finetune-v1
# Локальный диск Windows:
# MODEL_PATH=C:/models/e5-credit-finetune-v1/final
# Локальный диск Linux:
# MODEL_PATH=/srv/models/e5-credit-finetune-v1/final
# S3 — существующий bucket/prefix с содержимым model/:
# MODEL_PATH=s3://bucket/e5-credit-finetune-v1
```

Короткое HF-имя использует SHA из config/hf-deployment.lock.json. Для другого
HF-репозитория укажите @<SHA> прямо в MODEL_PATH. Допустимы file:// URI и обычные
локальные пути; неоднозначный относительный путь начинайте с ./.
Старые MODEL_SOURCE/HF_MODEL_ID/HF_MODEL_REVISION остаются совместимыми, но не
нужны: MODEL_PATH имеет приоритет. Источник не меняется автоматически при ошибке.

Аутентификация задаётся отдельно от адреса:
- Private HF: HF_TOKEN с read-доступом к репозиторию. На VPS рекомендуется
  отдельный read-токен; локально может использоваться сохранённый HF CLI login.
- Private S3: стандартная AWS credential chain / IAM role или
  AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN, AWS_DEFAULT_REGION.
  Для MinIO и других совместимых сервисов есть необязательный S3_ENDPOINT_URL.
  Доступ к реальному S3 не нужен для работы из HF/локальной папки.
- FastAPI: ML_INTERNAL_API_KEY, случайный секрет минимум 32 символа.

Секреты не добавляются в Git и не помещаются в MODEL_PATH. Settings читает
fastapi/.env. Кэш задаётся HF_CACHE_DIR (также используется S3); обычно достаточно
значения по умолчанию. HF_LOCAL_FILES_ONLY=true разрешает только готовый HF-кэш.

```powershell
uv sync --frozen --python 3.11
uv run --frozen python -m scripts.verify_model --smoke
uv run --frozen python -m app.server
```

Скачивание выполняется только при startup, далее inference идёт из проверенной
локальной папки CPU float32. Проверяются manifest, artifact SHA и все файлы.
На S3 ожидаются finetune-manifest.json и девять файлов из model/ с исходными
байтами. S3-ветка поддержана кодом и unit-тестами; реальный bucket не создавался.
При ошибке доступа/manifest startup останавливается, без fallback.
Перед первой HF-загрузкой уберите внешние HF_HUB_OFFLINE=1/TRANSFORMERS_OFFLINE=1.

## Docker Compose

Та же переменная MODEL_PATH задаётся в корневом .env. Compose заранее монтирует
fastapi/models в /models read-only; локальное значение внутри контейнера:
MODEL_PATH=/models/e5-credit-finetune-v1/final. Для HF и S3 меняется только
MODEL_PATH; соответствующие секреты доступа задаются отдельно.

Кэш постоянный, writable volume /model-cache. На Linux HF-кэш с симлинками
превращается в обычную папку для строгой проверки SHA: предусмотрите примерно
1 ГБ диска под snapshot и runtime-копию. У ML есть сеть исходящего доступа;
порт API по умолчанию наружу не публикуется. Остальные параметры Java/БД — по
корневому .env.example. Пустой RECOMMENDATION_MAX_COSINE_DISTANCE выбирает F1-порог.

## Идентичность, API, порог

| Параметр | Значение |
|---|---|
| Model ID | local/e5-credit-finetune-v1 |
| Artifact SHA-256 | 116acca8c00237091e511ea6e96a2959ad1345d9439b8c5a9c7fc2c29b9012e8 |
| SHA-256 весов | 502f9765a9cebed997794d64dcdc905721d0ca7b0c47a66262f227ea42a63b4c |
| Размер весов | 470637416 байт |
| База | intfloat/multilingual-e5-small, SHA 614241f622f53c4eeff9890bdc4f31cfecc418b3 |
| Размерность / длина | 384 / 512 токенов с prefix и special tokens |
| Runtime | CPU float32, batch 4, threads 2 / interop 1 |
| Минимальный similarity | 0.47622181475162506 |
| Максимальная distance | 0.5237781852483749 |

Источники истины: config/finetuned-model.lock.json и finetuned-selection-policy.json.
Порог выбран по максимуму micro F1 на calibration. Веса не менялись. В историческом
резервном ZIP осталась первоначальная F0.5-политика; текущая берётся из config.
Файлы model/ изменять нельзя: их точные байты покрыты manifest.

Java вызывает POST /api/v1/recommendations/rank-java с внутренним Bearer key.
Основной /rank использует X-Internal-API-Key. /api/v1/model-info показывает SHA
и порог; /health/live и /health/ready открыты. Формат API не зависит от источника:
возвращаются все кандидаты, рекомендуются 0…topK первых, максимум 3. Java определяет
eligibility и кредитные решения; cosine не является вероятностью одобрения.
Словарь, OpenAPI, JSON Schema и примеры — в config/, contracts/, examples/.

## Обучение и качество

Train: 1500 профилей / 300 семейств, 10610 пар (2060 positive). Full fine-tuning,
OnlineContrastiveLoss margin 0.5, 2 эпохи, 1328 шагов, batch 16, LR 2e-5,
weight decay 0.01, warmup 10%, seed 20261024, BF16 autocast на RTX 4070 Laptop.
CPU и CUDA зависимости закреплены раздельно. Подробности —
experiments/e5-credit-finetune-v1.json и scripts/train_e5.py.

Development 180 использовался для checkpoint, calibration 180 — для порога.
Первоначальный final90 и diagnostic15 уже просмотрены. Тексты/familyId обучения
и исходных evaluation-splits не пересекались; каталог из 15 продуктов общий.
Метки SYNTHETIC_PROPOSED требуют экспертной проверки. Это не доказательство
качества на реальных клиентах или новых продуктах.

```powershell
uv run --frozen python -m scripts.evaluate_active_model
uv run --frozen python -m scripts.evaluate_active_model --dataset evaluation/diagnostic-15.json --output reports/diagnostic15.json
```

Без перенастройки порога диагностический replay даёт:

| Набор | Precision | Recall | F1 | TP/FP/FN |
|---|---:|---:|---:|---:|
| finetune-test 90 | 91.85% | 96.12% | 0.9394 | 124/11/5 |
| diagnostic15 | 89.47% | 85.00% | 0.8718 | 17/2/3 |

`evaluate_finetune` — исторический эксперимент с F0.5, не проверка текущей политики.
Для готового inference повторное обучение не нужно.

## Повторная передача на HF и CI

```powershell
uv run --frozen python -m scripts.prepare_hf_package --output models/hf-export-new
uv run --frozen hf auth login
uv run --frozen hf upload thedauns/e5-credit-finetune-v1 models/hf-export-new . --private
```

После загрузки зафиксируйте SHA нового HF-коммита в .env. Не загружайте всё рабочее
дерево: подготовленный пакет содержит только явно разрешённые файлы без секретов.

CI contracts работает без весов. Ручные model-package / real-java требуют GitHub
Variable MODEL_PATH и соответствующие Secrets HF_TOKEN / AWS credentials. Они проверяют download,
SHA, CPU smoke и Java-цепочку. Git LFS для нового checkout не нужен.
Исходная E5 и model card checkpoint помечены MIT;
источник базы закреплён Git SHA в lock-файле.
