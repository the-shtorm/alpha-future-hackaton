# Кредитный скоринг SBA v2

Активная политика новых ревизий: `data-policy-3.0-sba-annuity-1`.
Основная модель: **`sba-scoring-v2`**, выбранная №5 (`mixed-v1-0051`), native
CatBoost, полный NAICS. Предыдущая `sba-scoring-v1` сохранена без изменений.
Положительный класс `LoanStatus=1` означает списание; `0` — полное погашение.
Модель даёт вероятность списания SBA, решение принимает Java вместе с финансовыми
и документарными проверками. Результат всегда демонстрационный.

## Данные и качество

V2 — точный экспорт выбранных весов и исходного sigmoid-калибратора без нового
обучения. Случайные целые годы, seed разбиения137, seed модели42: fit FY2011,
2013,2014,2016,2017,2018,2020; early stopping FY2019; calibration FY2012;
threshold FY2015; случайный исторический тест FY2010. Все development outcomes
известны до2022-10-01. FY2023 исключён из обучения/калибровки/подбора порога.

Фиксированный исследовательский порог: **p>=0.167204479067272**. На одной FY2023
(9963 кредита,1728 списаний):

| Модель | Precision | F1 | Recall |
|---|---:|---:|---:|
| V2, выбранная №5 | 58.958130% | 64.040190% | 70.081019% |
| V1, прежний фаворит при t=0.15283707537791144 | 49.094437% | 46.365302% | 43.923611% |

Это историческая, уже просмотренная validation, не новый независимый тест.
Желаемые85/55 и допустимые84/53 не достигнуты. На FY2024 у V2 precision37.25%,
F1 43.27%, recall51.61%; на FY2025 —3.43%/5.08%/9.76%; FY2026 содержит0 списаний,
поэтому recall не определён. Эти метрики не усредняются.
Пакет, точные счётчики и provenance: [sba-scoring-v2 на HF](https://huggingface.co/thedauns/sba-scoring-v2/tree/5a0049417dae97bdc8a341c89c705d7505563645/model).
Release approval в manifest означает выбранный пользователем demo-пакет с
проверенными целостностью и воспроизведением, не одобрение для банковского production.

### Сохранённая история V1

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

```dotenv
MODEL_PATH=thedauns/e5-credit-finetune-v1
SCORING_MODEL_PATH=thedauns/sba-scoring-v2
```

E5 получается через MODEL_PATH (local/HF/S3), без передачи weights через Git/LFS.
Скоринг v2 хранится в публичном HF; исходные scoring-пакеты v1/v2 удалены из Git. Их исторические
коммиты не переписывались. Веса, калибровка, пороги и API не менялись.
Короткий адрес HF закреплён immutable revision в config/scoring-hf.lock.json.
Подробности и проверка без E5: [SCORING_HF.md](../fastapi/SCORING_HF.md).

В существующем `.env` задайте, сохранив остальные значения:

```dotenv
SCORING_ENABLED=true
SCORING_MODEL_PATH=thedauns/sba-scoring-v2
HF_TOKEN=
HF_LOCAL_FILES_ONLY=false
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
- `GET /api/v1/scoring/model-info`: версии, класс/NAICS, `operatingThreshold`, counters inflight/completed/failed/busy.

OpenAPI и JSON Schema находятся в `fastapi/contracts/`. Сумма USD — decimal string
с двумя знаками, ставка — строка в процентных пунктах (до пяти знаков), срок —
строгий int 1..360, два Boolean строгие; неизвестные поля запрещены.
Java переводит RUB / 90.00 один раз, `HALF_UP`. Балл = round-half-up(100*(1-p)).
Решение использует исходную вероятность, не восстанавливает её из балла.
Формула балла у V2 та же, что у V1:100*(1-p) с округлением HALF_UP.
`operatingThreshold` закрепляет исследовательскую точку сравнения; финансовая
политика Java ниже по-прежнему использует собственные границы риска/PTI.

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

Для v2 проверены точное воспроизведение вероятностей/решений на всей FY2023 и
реальный native-пакет через локальный API: readiness, model-info, evaluate,
неизменная формула балла, отказ при неверном pin и загрузка сохранённого v1.
После слияния с cookie-session [полный Docker-стенд v2](agents/artifacts/2026-10-26-cookie-scoring-merge/cookie-four-outcomes.json)
прошёл через nginx cookie/CSRF → Java → E5/SBA → PostgreSQL: все четыре исхода,
одобрение и контрпредложение завершены DISBURSED. Скоринг загружается с HF.
Приведённые ниже исторические full-stack и latency-измерения относятся к V1.

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

Для возврата именно V1 сохранён pin; сам пакет нужно предоставить из проверенной
внешней или резервной копии. Например, положить его в fastapi/models/rollback-v1:

```sh
cp fastapi/config/scoring-model-v1.lock.json fastapi/config/scoring-model.lock.json
SCORING_MODEL_PATH=/scoring-models/rollback-v1 docker compose up -d --build --no-deps fastapi
```

Для standalone задайте `SCORING_MODEL_PATH=models/rollback-v1`.
После отката путь и pin должны соответствовать одной версии: несовпадение даёт503,
автоматической подмены модели нет. E5 и сохранённые исторические решения не меняются.
