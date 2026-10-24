# Передача дообученной E5

## Что передаётся с веткой

Готовый inference checkpoint находится в `fastapi/models/e5-credit-finetune-v1/final/`.
`model.safetensors` размером 470637416 байт хранится через **Git LFS**. Остальные
девять файлов — tokenizer, конфигурации, model card и manifest — входят в Git.
Базовые веса, training checkpoints, окружения, логи и локальный ZIP не передаются.
Для запуска готовой модели повторное обучение и загрузка исходной E5 не нужны.

После публикации ветки получать её нужно с установленным Git LFS:

```powershell
git lfs install
git clone --branch fast_api https://github.com/the-shtorm/alpha-future-hackaton.git
cd alpha-future-hackaton
git lfs pull
git lfs fsck
cd fastapi
uv sync --frozen --python 3.11
uv run --frozen python -m scripts.verify_model --smoke
```

Для существующего checkout после обновления ветки достаточно `git lfs pull`.
Авторизация GitHub нужна также для LFS, если репозиторий закрытый. Файл весов в
рабочем дереве должен иметь указанный размер, а не быть маленьким LFS pointer.
`verify_model` проверяет все SHA, manifest и реальный CPU inference без сети.

Пока ветка/новые коммиты и LFS object не отправлены, этих файлов на GitHub может
не быть. Сам факт локального commit или наличия pointer не доказывает загрузку
бинарного LFS object. На машине автора `git lfs fsck` проверяет только локальный кэш.

## Идентичность и текущая политика

| Параметр | Значение |
|---|---|
| Model ID | `local/e5-credit-finetune-v1` |
| Artifact SHA-256 | `116acca8c00237091e511ea6e96a2959ad1345d9439b8c5a9c7fc2c29b9012e8` |
| SHA-256 model.safetensors / LFS OID | `502f9765a9cebed997794d64dcdc905721d0ca7b0c47a66262f227ea42a63b4c` |
| Базовая модель | `intfloat/multilingual-e5-small` |
| Git revision базовой модели | `614241f622f53c4eeff9890bdc4f31cfecc418b3` |
| Размерность / длина | 384 / максимум 512 токенов вместе с prefix и special tokens |
| Runtime | CPU, float32, batch 4, Torch threads 2, interop 1 |
| Минимальный cosine similarity | `0.47622181475162506` |
| Максимальная cosine distance | `0.5237781852483749` |
| Критерий порога | максимум micro F1 на calibration, затем precision и меньшая distance |

Источники истины — `config/finetuned-model.lock.json`,
`config/finetuned-selection-policy.json` и `final/finetune-manifest.json`.
Весовой SHA и artifact SHA различаются: второй хеширует полный набор модельных
файлов. Runtime при несовпадении завершает startup, автоматической подмены нет.
Не изменяйте файлы внутри final/: их точные байты закреплены manifest.

В локальном историческом ZIP сохранён первоначальный F0.5-порог. Если используете
этот резервный архив, действующий F1-порог всё равно берётся из config репозитория.
Архив и metadata первоначального эксперимента не являются текущей runtime policy.

## Запуск и интеграция

Из корня репозитория настройте локальный `.env` по `.env.example`, включая
случайный `RECSYS_API_KEY` не короче 32 символов и обязательные параметры БД.
Существующий `.env` не перезаписывайте. Для ML:

```dotenv
RECSYS_MODEL_VARIANT=finetuned
RECSYS_MODEL_PATH=./fastapi/models/e5-credit-finetune-v1/final
RECOMMENDATION_MAX_COSINE_DISTANCE=
```

Пустой override выбирает F1-порог из config. `docker compose up -d --build`
монтирует checkpoint read-only. В образ веса не копируются. Обычная конфигурация
не публикует ML-порт наружу; для localhost существует `compose.dev.yaml`.
ML runtime работает offline и без CUDA. Ключи и содержимое запросов не логируются.

Java вызывает `POST /api/v1/recommendations/rank-java` с внутренним Bearer key.
Основной ML endpoint — `POST /api/v1/recommendations/rank` с X-Internal-API-Key.
OpenAPI и JSON Schema: `contracts/`, примеры: `examples/`.
`GET /api/v1/model-info` с X-Internal-API-Key подтверждает текущие SHA и порог.
`/health/live` и `/health/ready` доступны без ключа.

Java определяет допустимость продуктов, суммы, сроки и кредитные решения.
ML возвращает **всех** переданных кандидатов с rank и cosine similarity;
`isRecommended=true` у 0…topK первых позиций, максимум трёх, прошедших порог.
Статусы и pendingConditions возвращаются неизменными. Score не является процентом
соответствия или вероятностью одобрения. Порог не изменяет порядок полного ranking.

## Обучение и данные

Код, данные и lock-файлы передаются вместе с моделью:

- `scripts/train_e5.py`, `scripts/finetune_utils.py`: full fine-tuning с
  OnlineContrastiveLoss, margin 0.5; известные positives исключены из negatives.
- 1500 train-профилей / 300 семейств, 10610 пар (2060 положительных, 8550 отрицательных).
- Две эпохи, 1328 шагов, batch 16, LR 2e-5, weight decay 0.01, warmup 10%, seed 20261024.
- CUDA BF16 autocast на RTX 4070 Laptop; экспортированные веса используются как float32.
- Development: 180 профилей, выбор checkpoint по AP; calibration: 180 для порога;
  первоначальный final: 90. Тексты и familyId между этими группами не пересекались.
- `evaluation/backend-products.json`: 15 синтетических продуктов; train, calibration,
  holdout, reranker-test и finetune-test находятся рядом. `diagnostic-15.json`
  содержит дополнительные 15 примеров, уже использованных для анализа ошибок.
- CPU зависимости: `pyproject.toml` / `uv.lock`; отдельное CUDA-окружение обучения:
  `training/pyproject.toml` / `training/uv.lock`. Для готового inference CUDA не нужна.
- `experiments/e5-credit-finetune-v1.json`: параметры, версии библиотек и исторические
  метрики первоначальной F0.5-политики. Текущий F1 описан отдельно в config и отчётах.

Все метки — **SYNTHETIC_PROPOSED**, не экспертная банковская оценка. Каталог общий
для всех частей; это проверка новых запросов к известным продуктам. Прежние final90
и diagnostic15 уже просматривались и теперь являются диагностическими наборами.
Они не доказывают качество на реальных клиентах или новых продуктах.

## Воспроизводимая проверка текущего F1-порога

Из `fastapi/`, после `git lfs pull` и `uv sync --frozen`:

```powershell
uv run --frozen python -m scripts.evaluate_active_model
uv run --frozen python -m scripts.evaluate_active_model --dataset evaluation/diagnostic-15.json --output reports/diagnostic15.json
```

Эти команды не обучают модель и не подбирают новый порог. При пустом override
ожидается приблизительно следующее (CPU float32, числовой допуск на границах):

| Уже просмотренный набор | Precision | Recall | F1 | TP / FP / FN |
|---|---:|---:|---:|---:|
| finetune-test, 90 | 91.85% | 96.12% | 0.9394 | 124 / 11 / 5 |
| diagnostic-15 | 89.47% | 85.00% | 0.8718 | 17 / 2 / 3 |

У нового порога выше recall, но встречаются лишние рекомендации и ошибочные отказы.
Синтетическая разметка требует проверки ML-разработчиком/экспертом.
`scripts.evaluate_finetune` — отдельный исторический эксперимент с повторной
калибровкой F0.5; для проверки текущей F1-политики используйте evaluate_active_model.

## Проверки пакета и CI

CI `model-package` получает веса через checkout с `lfs: true`, проверяет Git LFS,
контрольные суммы и offline CPU smoke. `contracts` не скачивает крупные веса и
использует fake encoder. Ручной `real-java` проверяет обе модели и Java-цепочку.

Полный локальный pytest с исходной и дообученной моделями требует подготовленных
базовых весов, `RUN_REAL_MODEL_TESTS=1` и `RUN_FINETUNED_MODEL_TESTS=1`.
Для inference и проверки опубликованного checkpoint достаточно verify_model.

Исходная E5 помечена MIT в её
[model card на закреплённом revision](https://huggingface.co/intfloat/multilingual-e5-small/blob/614241f622f53c4eeff9890bdc4f31cfecc418b3/README.md).
Model card экспортированного checkpoint также указывает MIT. Авторство исходной
E5 принадлежит её авторам. Этот пакет не является реальным предложением банка и
не меняет лицензию остального кода репозитория.
