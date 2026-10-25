# Кредитный скоринг SBA v1

Активная политика новых ревизий: `data-policy-3.0-sba-annuity-1`.
Модель: `sba-scoring-v1`, native CatBoost, 1311 деревьев, полный NAICS.
Положительный класс `LoanStatus=1` означает списание; `0` — полное погашение.
Модель даёт вероятность списания SBA, решение принимает Java вместе с финансовыми
и документарными проверками. Результат всегда демонстрационный.

## Данные и качество

Исходный CSV сохранён неизменным в `data/scoring/raw/` и исключён из Git.
Хеш, точная схема и когорты: `fastapi/scoring_training/config/dataset.lock.json`.
461559 строк, 23 колонки; X содержит только девять разрешённых признаков.
Обучение/подбор: FY2010–2014 / FY2015–2016. Переобучение: FY2010–2016.
Sigmoid-калибровка: только FY2017. Веса и калибратор зафиксированы до test/transfer.

| Часть | ROC-AUC | Average Precision | Log Loss | Brier |
|---|---:|---:|---:|---:|
| Test FY2018–2019 | 0.926857 | 0.601910 | 0.197731 | 0.056851 |
| Transfer FY2020–2026 | 0.796361 | 0.416350 | 0.280348 | 0.068943 |
| Test: константа train | 0.500000 | 0.098478 | 0.327181 | 0.089575 |

Полный пакет с метриками по группам, порогам, calibration bins и диаграммой:
[models/sba-scoring-v1](../fastapi/models/sba-scoring-v1/README.md).
Все 32 опыта и диагностика: [эксперимент](../fastapi/experiments/sba-scoring-v1.json).
Воспроизведение: [CPU-обучение](../fastapi/scoring_training/README.md).

Ограничения: это ретроспективная выборка завершённых американских кредитов, без ID
заёмщика. Историческая доступность изменяемого срока не подтверждена: без срока
validation ROC-AUC снизился с 0.970 до 0.681. Калибровка меняется между когортами.
Прямые outcome-поля не входят в X, но это не доказывает отсутствие всех косвенных
утечек и не подтверждает российскую банковскую PD. Ставки российского демо-каталога
выше train-диапазона 0.66–11.52%; прогноз сопровождается предупреждением.

## Получение и запуск

```sh
git lfs install
git lfs pull
git lfs fsck
```

В Git/LFS передаётся только выбранный SBA-пакет и используемый checkpoint E5.
Пробные модели и полный CSV не передаются. Веса E5, её SHA и пороги сохранены.
В этой задаче созданы только локальные коммиты. До явной публикации коммитов и
LFS-объекта SBA пакет может быть недоступен на другой машине.

В существующем `.env` задайте, сохранив остальные значения:

```dotenv
SCORING_ENABLED=true
SCORING_MODEL_PATH=./fastapi/models/sba-scoring-v1
SCORING_URL=http://fastapi:8000/api/v1/scoring/evaluate
DEMO_ASSESSMENT_ENABLED=false
```

Compose использует существующий `RECSYS_API_KEY` для обоих внутренних API.
Ключ нужен случайный, минимум 32 символа; он не попадает в frontend. Отдельно
заданы пароли БД и demo-owner/demo-bank согласно `.env.example`. Существующий
`.env` не перезаписывать. После конфигурации:

```sh
docker compose up -d --build
```

Standalone FastAPI сохраняет `SCORING_ENABLED=false` по умолчанию. В основном
Compose после приёмки включён выбранный demo-пакет; его volume read-only,
manifest SHA закреплён в `fastapi/config/scoring-model.lock.json`. Для backend
без Compose переменные `SCORING_URL` и `SCORING_API_KEY` задаются отдельно.
Неправильный пакет не заменяется fixed weights. Для несинтетического продукта
SBA demo-оценка не разрешает автоматическое положительное решение.

Перед банковским расчётом нужен действующий серверный макроконтекст через
`POST /bank/macroeconomic-contexts` и проверенные документы. Автоматической
загрузки текущей ставки ЦБ нет. Значения ставки в приёмке — synthetic fixtures.

## Внутренний HTTP и диагностика

Bearer-аутентификация, ключ только на сервере:

- `POST /api/v1/scoring/evaluate`: строгий `sba-scoring-1`, UUID и девять признаков.
- `GET /api/v1/scoring/ready`: 200 или 503 MODEL_NOT_READY.
- `GET /api/v1/scoring/model-info`: версии, класс/NAICS, counters inflight/completed/failed/busy.

OpenAPI и JSON Schema находятся в `fastapi/contracts/`. Сумма USD — decimal string
с двумя знаками, ставка — строка в процентных пунктах (до пяти знаков), срок —
строгий int 1..360, два Boolean строгие; неизвестные поля запрещены.
Java переводит RUB / 90.00 один раз, `HALF_UP`. Балл = round-half-up(100*(1-p)).
Решение использует исходную вероятность, не восстанавливает её из балла.

Один inference-поток, максимум четыре принятых запроса, ожидание допуска до секунды.
Отмена HTTP не освобождает слот до завершения вычисления. Валидация — 422,
аутентификация — 401, неготовность/перегрузка — 503; внутренние ошибки не раскрываются.
Readiness ранжирования `/health/ready` сохраняет свой смысл независимо от scoring.

Всегда возвращаются `SBA_US_TO_RU_DEMO`, `TERM_HISTORY_UNCONFIRMED`; дополнительно —
`AMOUNT/RATE/TERM_OUT_OF_RANGE`, `UNSEEN_NAICS`, неизвестные/редкие категории.
Диапазоны и частоты вычислены на фактическом refit train. Редкость — менее 50 строк.
Выход за диапазон не обрезает признаки и не отменяет прогноз в demo-режиме.

Для наблюдения задержек/ошибок используйте HTTP-метрики и reasonCode/scoringErrorCode
решений; версии/предупреждения и исходы сохраняются в assessment_run. Распределение
рисков и OOD можно агрегировать по `output->>'sbaDefaultProbability'` и
`output->>'domainStatus'` в assessment_run, без вывода анкет в технические логи.

## Политика и история

`overdue > 0.20` — hard reject без ML. После обязательных проверок и Payments:
`p_final=min(1,p_sba+0.50*overdue)`, PTI=(текущие платежи+новый платёж)/средняя выручка.
Одобрение: p_final ≤0.15 и PTI ≤0.40; p_final >0.35 — отказ. Промежуточный риск или
нагрузка допускают только разрешённое продуктом контрпредложение.

Альтернативная ставка max(base,key+5+20*initial_p_final), один раз HALF_UP до пяти
знаков. Сумма ищется по той же Payments с комиссиями до копейки, срок растёт
максимум на 12 месяцев только при перегрузке и явном разрешении. ML не участвует
в двоичном поиске суммы. Единственный кандидат повторно оценивается; контрпредложение
возможно при p_final ≤0.35, PTI ≤0.40 и одной версии пакета в обоих ответах.

Обе успешные оценки имеют собственные строки assessment_run. FK решения и flat
поля условий соответствуют выбранному варианту. Старые ревизии используют свою
policyVersion, включая rule_version при выдаче. Исторические решения/предложения
не пересчитываются. Переход на новую политику требует новой подтверждённой ревизии.

## Приёмка, память и откат

[Полный HTTP-стенд](../fastapi/experiments/sba-full-stack-v1.json): nginx/frontend →
Java 21 → реальные E5/SBA → PostgreSQL 17. Все четыре решения пройдены; APPROVED
и COUNTEROFFERED завершились DISBURSED. Временный стенд и его том удалены.

[HTTP benchmark](../fastapi/experiments/sba-scoring-http-acceptance-v1.json): p95
одиночного scoring 10.08 мс, p99 при четырёх запросах 35.63 мс, с E5 34.25 мс.
Это измерение локального Docker Desktop Linux/amd64 на ARM с эмуляцией, не SLA
для любого сервера. E5 ranking до/после нагрузки совпал полностью.

Пик FastAPI 1.01 GiB при лимите 2 GiB; сумма пиков четырёх сервисов 1.37 GiB.
Основной Compose ограничивает все контейнеры суммарно 3.75 GiB, включая pgAdmin.
С плановым резервом 2 GiB под ОС это 5.75 GiB из 6 GiB. Резерв ОС — предположение,
не измерение потребления пользовательского macOS или других приложений.

Повторить отдельную приёмку после сборки образов, не затрагивая основной проект:

```sh
docker build -t alpha-future-backend:scoring-acceptance .
docker build --platform linux/amd64 --target runtime -t alpha-future-fastapi:scoring-acceptance fastapi
docker build -t alpha-future-frontend:scoring-acceptance frontend
uv sync --project fastapi/scoring_training --frozen
fastapi/scoring_training/.venv/bin/python fastapi/scripts/scoring_stack_acceptance.py
```

Откат: выставить `SCORING_ENABLED=false` и пересоздать только FastAPI:

```sh
docker compose up -d --no-deps fastapi
```

E5 продолжит ранжирование. Новая политика вернёт REQUEST_INFO с
`reasonCode=ASSESSMENT_UNAVAILABLE` и техническим `scoringErrorCode`; автоматического
fallback на DemoAssessment нет. Сохранённые оценки, решения и предложения остаются.
Чтобы вернуть скоринг, восстановить проверенный пакет/pin и SCORING_ENABLED=true.
Не заменять опубликованный пакет в его каталоге: новое обучение — новая версия/путь.
