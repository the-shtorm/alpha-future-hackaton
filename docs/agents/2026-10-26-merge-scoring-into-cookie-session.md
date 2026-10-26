# Локальное слияние scoring_model в cookie-session

## Запрос и исходное состояние

Пользователь поручил локально слить `scoring_model` и сразу проверить совместимость.
В репозитории целевая ветка называется `cookie-session` (через дефис); отдельная
`cookie_session` не создавалась. Исходный target HEAD: `911fa84`, source: `3dd8664`.
Рабочее дерево перед слиянием чистое. Push и перезапуск основного stack не входят
в задачу. Слияние начато `git merge --no-ff --no-commit scoring_model`.

## Разрешение конфликтов

Сохраняются cookie/CSRF frontend и Java, E5 MODEL_PATH (local/HF/S3), CI model-path
исправление целевой ветки. Добавляются native scoring v2, HF/local источник,
Java финансовая policy и scoring tests из source. В конфликтных Java fixtures
сохранены обе настройки: cookie-secure=false и scoring stub. README и индекс
отчётов объединены с сохранением исторических записей. Из Docker mounts сохранён
корень /models для E5 и отдельный /scoring-models для документированного local scoring.
В auto-merged YAML и Settings удалены дубли общих HF/cache полей.

Lock строится из scoring версии с добавлением boto3 из cookie-session; native
версии CatBoost/pandas/sklearn/numpy сохраняются. python-dateutil меняется с 3.0.0
на 2.9.0.post0 по ограничению botocore. Offline resolution первоначально не смог
найти metadata; online uv lock успешно разрешил 85 пакетов. pip exports пересозданы
штатным scripts.export_requirements. Загруженные модели остаются вне Git.

Для проверки реального browser пути acceptance script расширен --cookie-auth:
отдельные owner/bank cookie jars, CSRF, nginx /api, отсутствие accessToken в login
JSON, HttpOnly session. Внутренний Java→FastAPI auth сохраняется отдельно.

## Выполненные проверки

- `uv sync --frozen --python 3.11`, export_requirements, Ruff app/scripts/tests,
  format acceptance script, `git diff --check` прошли. YAML compose.yaml,
  compose.ml-test.yaml, compose.session-test.yaml и CI дополнительно разобраны
  strict loader без дублирующихся mapping keys; Compose config --quiet прошёл.
- Полный Windows pytest с `python -X utf8`: **562 passed, 9 skipped**, coverage
  **96.48%**, **64.59 s**. Пропущены opt-in real-model проверки и Windows symlink.
- Полный Linux test image: настоящие base/finetuned E5 и native scoring,
  `--network none --memory 2g --read-only`, tmpfs 256 MiB:
  **568 passed, 3 skipped**, coverage **98.18%**, **128.37 s**.
  Пропуски включают legacy v1, отсутствующий в текущем пакете; порог coverage 95%
  не снижался. Native scoring tests отдельно: **2 passed, 1 skipped**.
- Native v2 после объединения зависимостей сохранил вероятность
  **0.2525274156209339**, score **75**, threshold **0.167204479067272**.
- Настоящая E5 разрешена по закреплённому HF revision из существующего кэша,
  проверена по manifest, CPU smoke float32 shape **[2,384]** прошёл. Для локальных
  acceptance mounts подготовлена игнорируемая models/cookie-scoring-merge-e5.
- `npm test`: **33 passed**. Системный Node 22.17.1 первоначально не прочитал .ts;
  повтор с NODE_OPTIONS=--experimental-strip-types прошёл. Production TypeScript/
  Vite build в Docker Node 22-alpine прошёл. Source frontend не менялся.
- Maven/Java 21 `verify` в отдельном maven container с Docker socket и Testcontainers
  PostgreSQL: **71 tests, 0 failures, 0 errors, 1 skipped** (**70 passed**),
  Spotless и package прошли. Пропущен opt-in realScoringCompletesFourDecisionJourneys;
  настоящие четыре HTTP-исхода отдельно проверены ниже. Использовался собственный
  volume cookie_scoring_merge_m2, без изменения основного PostgreSQL.
- Собраны отдельные runtime/test FastAPI, backend, frontend images
  `*:cookie-scoring-merge` / `*:cookie-scoring-merge-tests`.
- `scripts.check_cookie_https.py` с отдельными образами: **все 6 checks passed**:
  проверка TLS-сертификата, отказ чужому CA, Secure/Host cookie attributes,
  Secure cookie не отправляется по HTTP, CSRF/повторные записи, удаление при logout.
  [JSON](artifacts/2026-10-26-cookie-scoring-merge/https-cookies.json).
- `scripts.scoring_stack_acceptance --cookie-auth`: **passed**. Реальный путь
  nginx /api → owner/bank cookie+CSRF → Java → E5/native HF scoring → PostgreSQL.
  APPROVED/P07 и COUNTEROFFERED/P01 дошли до DISBURSED; DECLINED и REQUEST_INFO
  корректны. Ranking READY во всех случаях, максимум три рекомендации. В audit
  четыре assessments, три связанных decisions, только model sba-scoring-v2.
  В JSON cookie login нет accessToken; проверены HttpOnly и отказ без CSRF.
  [Полный JSON](artifacts/2026-10-26-cookie-scoring-merge/cookie-four-outcomes.json).
- Совместная загрузка **обеих моделей по HF identifiers** из одного read-only кэша
  в Docker `--network none --memory 2g` прошла. Настоящая E5 ранжирует, один native
  classifier остаётся в RAM для четырёх повторов scoring, ответы одинаковы,
  последующее E5 ранжирование неизменно. Snapshot SHA и artifact identity сохраняются.
  [Краткий результат](artifacts/2026-10-26-cookie-scoring-merge/dual-hf-offline.json).

## Исправленные проблемы проверки

Первый cookie full-stack запуск не прошёл login: изолированный compose.ml-test
публикует HTTP, а default SESSION_COOKIE_SECURE=true запрещал cookie отправку.
В этом тестовом Compose явно задано false; отдельная HTTPS-проверка сохраняет true
и подтверждает Secure. Production TLS-настройки не отключались. В первом ad-hoc
offline harness rank-java ошибочно вызывался с X-Internal-API-Key; исправлен на
требуемый внутренний Bearer, после чего проверки прошли. API auth не ослаблялся.

## Измерения и ограничения

В настоящем cookie four-outcome сценарии FastAPI peak **924581888 bytes (~882 MiB)**,
сумма пиков четырёх containers **1377259520 bytes (~1.28 GiB)**. Сумма container
limits **3.375 GiB** + расчётный резерв ОС **2 GiB** укладывается в бюджет 6 GiB;
резерв не измерялся, длительная production-нагрузка не имитировалась. p95 scoring
HTTP: **35.07 ms** sequential, **60.38 ms** concurrency 4, **69.70 ms** вместе с E5.
Без нового ML-обучения, калибровки или оценки банковского качества. Сохранены demo/
EXTRAPOLATION warnings; синтетические branch fixtures не являются quality holdout.
Ненулевые предупреждения Python относятся к deprecation Starlette/SentenceTransformers,
ошибок тестов нет. S3-путь E5 покрыт unit-тестами с fake client; реального S3 bucket
для интеграционного запроса не использовали. Git diff к target подтвердил неизменность
frontend/src, Accounts, BrowserSessions, Security и E5 local/HF/S3 source modules.

## Итог и Git

Конфликты всех десяти файлов разрешены; MODEL_PATH и SCORING_MODEL_PATH независимы,
оба сервиса используют общий постоянный HF cache без конфликтов. Текущие docs
обновлены под отсутствие Git/LFS weights и рабочую v2 cookie-интеграцию. Исторические
отчёты не переписывались. Завершение — локальный merge-коммит на cookie-session с
родителями 911fa84 и 3dd8664, вместе с исправлениями интеграционного test harness
и этим отчётом. Scoring_model не меняется, push не выполняется.
Основной пользовательский stack не пересоздавался; временные acceptance/TLS
containers и их DB/cache volumes удалены своими harness после проверки.
