# Единая документация и запуск для проверяющих хакатона

Дата: 2026-10-26. Статус: завершено. Ветка: `pre-docs`.

## Запрос и порядок работы

Сначала слить новые изменения `cookie-session` в `pre-docs` без предварительных
проверок. После слияния привести действующую документацию всего проекта к коду,
подготовить подробный Docker-запуск для проверяющих и проверить полный процесс.
По просьбе пользователя новые пользовательские руководства описывают рабочие
сценарии и настройку без перечня текущих багов. Исторические отчёты сохраняются
согласно `AGENTS.md`.

## Слияние

- Исходный `pre-docs`: `d7c6991`, рабочее дерево чистое.
- `git fetch origin`: `origin/cookie-session` обновлён до `f5c2a33`.
- До редактирования документации и без предварительного прогона проверок выполнен
  `git merge --no-ff origin/cookie-session -m 'Merge latest cookie-session fixes into pre-docs'`.
- Слияние без конфликтов: `16ede78`, родители `d7c6991` и `f5c2a33`.
- В слитой версии присутствуют банковский UI, действия принятия предложения,
  демонстрационного договора/выдачи и явная замена версий документов.

## Изменения и deliverables

| Область | Файлы и содержание |
|---|---|
| Точка входа | `README.md`, новый `docs/README.md`: единая навигация, роли, актуальные возможности и архитектура |
| Для проверяющих | Новый `docs/hackathon-start.md`: требования, запуск, доступы, два браузерных контекста, макроконтекст, параметры заявки, документы, решение, акцепт, подписание, выдача, другие исходы, остановка |
| Конфигурация | Новый `docs/configuration.md`, `.env.example`: переменные, секреты, порты, модели, тома и изоляция экземпляров |
| Запуск | Новые `scripts/setup-demo.ps1`, `setup-demo.sh`, `start-demo.ps1`, `start-demo.sh`: заполнение семи пустых секретов, сохранение существующих значений, идемпотентность, build/up/wait |
| Compose | `compose.yaml`: frontend healthcheck через nginx→Java→БД, передача `HF_HUB_DISABLE_XET`, стартовое окно ML healthcheck 30 минут и шесть повторов |
| API и формы | `docs/backend-api.md`, `backend-fields-v3.md`, `preliminary_form.md`, `postman-testing.md`: 15/13/17 полей, автоматический E5, cookie/CSRF, текущий HTTP-путь |
| Политика и данные | `docs/backend-plan.md`, `data-policy.md`, `data-dictionary.md`, `credit-scoring.md`, `form-storage-contract.md`: SBA v2, аннуитет/PTI, встречные условия, версии и ревизии |
| База | `docs/database-design.md`, `database-erd.mmd`: фактические сущности и V1–V11 |
| Рекомендации | `docs/query_passage_mvp.md`, `ranking-exchange.md`, новый `contracts/README.md`: шесть query-полей, автоматический обмен и технический экспорт/импорт |
| Frontend и проверки | `frontend/README.md`, `docs/validation.md`, `code-style.md`: текущие экраны, сохранение и реальные команды инструментов |
| ML | `fastapi/MODEL_HANDOFF.md`, `SCORING_HF.md`, `scoring_training/README.md`, `experiments/README.md`, `data/scoring/README.md`: активные пакеты, источники, воспроизводимость и история исследований |
| Исходные материалы | Новый `docs/reference/README.md`, навигационные пометки у исходных требований и двух исторических планов; четыре отсутствовавших приложения анализа сохранены как названия без несуществующих ссылок |
| Тестовый файл | Новый `docs/demo/sample-document.pdf`: одностраничный синтетический документ без персональных данных |
| Отчётность | Этот новый отчёт, строка в `docs/agents/log.md`, обезличенные артефакты проверки |

Завершённые отчёты `docs/agents/` и датированные ML-отчёты не переписаны.
Исторические research README и результаты сохраняют своё происхождение;
рабочая модель указана в действующем индексе. В JSON Schema ранжирования изменён
только title с MVP 1 на MVP 2, структура и проверки не менялись.

## Проверка штатного Docker-запуска

Использовался основной `compose.yaml`, проект `judge-docs-20261026`, отдельный
`work/documentation-launch/launch.env`, штатные порты и реальные E5/SBA.
Корневой пользовательский `.env` не редактировался. Секреты генерировались
локально, не печатались и не включались в Git/этот отчёт.

1. `scripts/setup-demo.ps1 -EnvFile work/documentation-launch/launch.env`.
2. `docker compose --env-file work/documentation-launch/launch.env --project-name judge-docs-20261026 build backend frontend fastapi` — exit 0.
   Все три образа собраны штатными Dockerfile, включая Java package и `npm run build`.
3. Для E5 использован ранее проверенный HF-кэш: его каталог скопирован read-only
   из `work/cookie-pre-docs-merge/model-cache` в новый одноимённый том тестового
   проекта. Исходный кэш не изменялся. Источники моделей в env оставлены штатными
   HF, `HF_LOCAL_FILES_ONLY=false`, `HF_TOKEN` пуст. SBA скачан автоматически в
   новый кэш. Полное время первого скачивания E5 из пустого кэша этим прогоном
   не измерялось.
4. `scripts/start-demo.ps1 -EnvFile work/documentation-launch/launch.env -ProjectName judge-docs-20261026` — exit 0, build + up с `--wait --wait-timeout 2400`.
5. Фактическое `docker compose ps`: пять сервисов running; у `postgres`, `fastapi`
   и `frontend` health=healthy. Backend и pgAdmin не задают отдельный healthcheck.
   `/health` и `/api/health` отвечают 200; frontend отдаёт production HTML.

## Сквозной HTTP-прогон

Запущен `python -X utf8 work/documentation-launch/stock_journey.py` — exit 0.
Сохранённый вариант с параметрами:
[stock-journey-check.py](artifacts/2026-10-26-documentation-launch/stock-journey-check.py).
Он предназначен для отдельного заранее запущенного тестового экземпляра;
`--env-file` задаёт его локальные пароли. Данные сценариев синтетические.

Проверены отдельные owner/bank cookie jars, обязательный CSRF на входе, `/me`,
автоматический E5-подбор с READY, выбор продукта, перенос формы, дополнение,
загрузка настоящего учебного PDF для каждого требования, скачивание точных байтов,
явная замена файла с историей/current, проверка новой версии банком, назначение,
подача и реальный SBA inference.

| Исход | Продукт | ML-оценок | Вероятность выбранного варианта | Итог |
|---|---|---:|---:|---|
| APPROVED | P07 | 1 | 0.006003678384059744 | Принят Offer, подписан учебный договор, DISBURSED |
| COUNTEROFFERED | P01 | 2 | 0.2525274156209339 | Акцепт по UUID/hash, подписан договор, DISBURSED |
| DECLINED | P01 | 1 | 0.2525274156209339 | Отказ сохранён |
| REQUEST_INFO | P01 | 0 | — | Недостающие сведения запрошены |

Агрегат БД: 4 заявки, 4 `assessment_run`, 3 решения со ссылкой на оценку,
2 демонстрационные выдачи, только `sba-scoring-v2`; Flyway history содержит
13 успешных записей (11 versioned + 2 repeatable).

[Результаты HTTP](artifacts/2026-10-26-documentation-launch/stock-journey-results.json),
[состояние сервисов](artifacts/2026-10-26-documentation-launch/compose-state.json),
[агрегаты БД](artifacts/2026-10-26-documentation-launch/database-audit.json).

## Дополнительные фактические проверки

- Windows PowerShell 5.1: отдельный fixture, генерация 48 hex-символов,
  сохранение существующего значения, совпадение hash после повторного setup — passed.
- Bash в Linux-контейнере: `bash -n` для двух скриптов, генерация, сохранение
  значения и идемпотентность — passed. Первый тестовый fixture заменял строку
  без учёта CRLF шаблона; исправлен шаблон замены в тестовом helper, затем
  повторный прогон завершился exit 0. Продуктовый Bash-скрипт не менялся.
- `docker compose ... exec -T fastapi python -m scripts.verify_model --smoke` —
  verified=true, artifact SHA `116acca8c00237091e511ea6e96a2959ad1345d9439b8c5a9c7fc2c29b9012e8`,
  CPU float32, shape 2×384, distance 0.5237781852483749.
- `docker compose ... exec -T fastapi python -m scripts.prepare_scoring_model --smoke` —
  verified=true, sba-scoring-v2, sigmoid-fy2012, threshold 0.167204479067272,
  контрольный прогноз 0.2525274156209339, score 75.
- Браузер: каталог 15 продуктов, вход demo-bank, очередь четырёх исходов,
  согласованные условия и «Средства перечислены»; [скриншот](artifacts/2026-10-26-documentation-launch/bank-disbursed.png).
- `docker compose ... down` без удаления томов, затем `up --detach --wait --wait-timeout 2400`
  — exit 0. Обновление страницы восстановило банковскую сессию и очередь с двумя
  выдачами. [Проверка повторного запуска](artifacts/2026-10-26-documentation-launch/restart-check.json).
- PDF создан ReportLab, извлечение кириллицы и одна страница проверены pypdf;
  рендер Poppler просмотрен, пересечений/обрезки нет. Использован навык PDF.
- Проверены локальные Markdown-ссылки в 51 файле действующей документации,
  источников и ML-материалов: 0 отсутствующих целей.
- `git diff --check` — exit 0; сообщения Git касаются нормализации LF/CRLF,
  ошибок whitespace нет.
- После проверки `docker compose ... down --volumes` — exit 0; удалены только
  одноразовые сервисы, сети и тома `judge-docs-20261026`, порты освобождены.

## Контракты, миграции и условия проверки

Публичный HTTP API, бизнес-алгоритм, модельные веса, lock-файлы и SQL-миграции
этой задачей не изменялись. Добавлены команды подготовки окружения и ожидание
readiness в конфигурации запуска. Пустые секреты `.env.example` заполняются setup;
существующие непустые значения сохраняются. Для нового экземпляра модельные
пакеты готовятся автоматически по закреплённым HF-источникам.

Это практическая проверка штатного запуска и синтетических ветвей интеграции.
Новая независимая оценка качества моделей и обучение не выполнялись. Полные
модульные suites заново не запускались; приведены только действительно
выполненные сборки, проверки и сквозные сценарии после слияния.

## Финальное Git-состояние

HEAD `16ede78`, ветка `pre-docs`. Merge выполнен локально; новые изменения
документации, setup/start и Compose оставлены в рабочем дереве для review.
Дополнительный commit/push не выполнялся. Основной `.env`, рабочие базы и исходные
модельные кэши пользователя не изменялись. `work/` и модельные веса игнорируются Git.
