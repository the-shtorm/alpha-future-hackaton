# Слияние обновлённой cookie-session в pre-docs и проверка пайплайна

Дата: 2026-10-26. Статус: завершено. Локальное слияние в pre-docs, без push.

## Запрос и ограничения

Проверить обновлённую ветку `cookie-session`, слить её в `pre-docs` и проверить работоспособность кредитного пайплайна. Разрешено локальное слияние и необходимые исправления обнаруженных проблем; push не запрошен. Сохранять пользовательские изменения и исторические отчёты, не выводить секреты и персональные данные.

## Исходное состояние

- Рабочая ветка `pre-docs`, HEAD `1909699` (`docs: preliminary project test`), рабочее дерево чистое.
- Локальная `cookie-session`: `2e88bd9`; до fetch её tracking-ветка показывает 45 новых коммитов.
- Предыдущий аудит находится в отдельном отчёте `2026-10-26-credit-pipeline-state-audit.md`; его результаты не считаются проверкой новых изменений.

## Выполненные действия и проверки

- Прочитаны AGENTS.md, текущие Git refs, состав проекта и доступные инструменты от предыдущей проверки.
- Начата синхронизация удалённых refs.
- `git fetch origin` выполнен успешно после разрешения доступа к .git/сети. Актуальный source: `origin/cookie-session` = `11167936d74cbe98ca552c50e3432b86cfcb60a9`.
- `git merge --no-ff --no-commit origin/cookie-session` в `pre-docs` прошёл без конфликтов. Входят 45 коммитов, включая интегрированный обученный SBA CatBoost v2. Сохраняется отдельный коммит pre-docs с прежним аудитом.
- В рабочей копии 21 Java-файл имел старые CRLF, несмотря на обязательный LF в .gitattributes. Концы строк приведены к LF без изменения содержимого; отдельного Git diff это не создало.
- Frontend `npm test`: 33/33 passed; TypeScript/Vite production build passed.
- Maven/Java 21 `verify javadoc:javadoc`: BUILD SUCCESS; 71 tests, 0 failures/errors, 1 opt-in real-model skipped (70 passed); Spotless проверил все 37 Java-файлов, JAR и JavaDoc собраны.
- Собраны отдельные образы `alpha-future-backend:pre-docs-merge` и `alpha-future-frontend:pre-docs-merge`: текущие проверенные JAR/dist поверх уже имевшихся локальных runtime-образов. Это проверка текущего приложения в контейнерах; полная пересборка Maven/Node stages исходных Dockerfile отдельно не заявляется.
- Начата сборка FastAPI test image из текущего штатного Dockerfile и uv.lock; подготовлены изолированные каталоги моделей/кэша в игнорируемых fastapi/models и work/cookie-pre-docs-merge.
- FastAPI runtime/test images из штатного Dockerfile собраны. Полный Linux pytest без сети, read-only root, memory limit 2 GiB: **564 passed, 7 skipped**, coverage **97.76%** при обязательном минимуме 95%. Ruff `app scripts tests`: all checks passed.
- HTTPS acceptance на новых backend/frontend images: все **6 checks passed**; [JSON](artifacts/2026-10-26-pre-docs-cookie-merge/https-cookies.json).
- Настоящий HF `sba-scoring-v2` проверен загрузчиком с закреплённым manifest и версиями библиотек; probability `0.2525274156209339`, score `75`, operating threshold `0.167204479067272`. [Metadata](artifacts/2026-10-26-pre-docs-cookie-merge/scoring-package.json).
- Дополнительные offline real-scoring package/API tests: **2 passed, 1 skipped**; пропущен необязательный rollback v1 без отдельного пакета.
- Получение E5 по Xet столкнулось с таймаутами. Повтор обычным HTTPS дал валидный последовательный префикс, но низкую скорость; начата ограниченная загрузка оставшихся диапазонов (6 connections) с обязательной проверкой полного SHA-256 из уже загруженного закреплённого manifest. Изменений загрузчика приложения и ослабления проверок нет.

## Результаты и ограничения

**Обновлённая cookie-session слита без конфликтов; сквозной демонстрационный backend-пайплайн работает с настоящими E5 и SBA CatBoost v2.** Предыдущий аудит о неподключённом обученном скоринге относится к старому HEAD и не описывает эту версию. Исторический отчёт сохранён без переписывания.

Локальная `cookie-session` обновлена fast-forward до `1116793` командой `git fetch . refs/remotes/origin/cookie-session:refs/heads/cookie-session`, без повторного обращения к серверу. Прикладное содержимое результата слияния совпадает с этой веткой: `git diff --cached --quiet cookie-session -- backend frontend fastapi compose.yaml compose.ml-test.yaml .github/workflows/recsys-tests.yaml .env.example` дал код 0. Незастейдженных прикладных изменений также нет.

### Настоящая HTTP-цепочка и четыре исхода

Запущен штатный `fastapi/scripts/scoring_stack_acceptance.py --cookie-auth` на отдельных runtime images, случайных loopback-портах и одноразовой БД. Транспорт: nginx `/api` → отдельные owner/bank HttpOnly-cookie + CSRF → Java 21 → настоящие E5 и native CatBoost → PostgreSQL 17. [Полный результат](artifacts/2026-10-26-pre-docs-cookie-merge/four-outcomes.json).

| Сценарий | Продукт | Результат |
|---|---|---|
| APPROVED | P07 | Акцепт → условное подписание → DISBURSED |
| COUNTEROFFERED | P01 | Акцепт точных альтернативных условий → условное подписание → DISBURSED |
| DECLINED | P01 | Ожидаемый отказ |
| REQUEST_INFO | P01 | Ожидаемый дозапрос при отсутствии финансового поля |

Во всех четырёх случаях автоматическое ранжирование было `READY`, число выделенных рекомендаций не превышало трёх. Проверены загрузка и банковская проверка документов, подача актуальной ревизии, сохранение ML-аудита: **4 assessment_run, 3 решения со ссылкой на оценку, только sba-scoring-v2**. Cookie-вход не выдаёт accessToken в JSON; login без CSRF отклонён.

Benchmark с той же настоящей E5 и SBA прошёл 50 последовательных, 100 конкурентных и 60 scoring-запросов вместе с E5 после прогрева. Порядок/ответы ранжирования остались неизменны. Scoring p95: **24.89 ms** последовательно и **78.70 ms** вместе с E5. Измеренный peak FastAPI: **869.01 MiB**. Это короткая проверка интеграции/нагрузки, не длительная production-проверка и не оценка качества модели.

### Проверки и фактические команды

| Проверка | Фактический результат |
|---|---|
| `git fetch origin`; `git merge --no-ff --no-commit origin/cookie-session` | Source 1116793, 45 входящих коммитов, конфликтов нет |
| `node work/pipeline-audit/tools/npm-10.9.2/package/bin/npm-cli.js --prefix frontend test` | **33 passed** |
| Тот же npm: `--prefix frontend run build` | TypeScript + Vite production build passed |
| `work/pipeline-audit/tools/apache-maven-3.9.9/bin/mvn.cmd --batch-mode --no-transfer-progress -f backend/pom.xml -Dmaven.repo.local=D:/prog/hackatons/alpha-future-hackaton/work/pipeline-audit/m2 verify javadoc:javadoc` | **BUILD SUCCESS**; 71 tests, 0 failures/errors, 1 skipped; 70 passed, Spotless/JAR/JavaDoc прошли |
| `docker build --target test -t alpha-future-fastapi:pre-docs-merge-tests ./fastapi` и `--target runtime -t alpha-future-fastapi:pre-docs-merge` | Оба штатных образа собраны с frozen uv.lock |
| Full pytest в test image: `--network none --memory 2g --read-only`, tmpfs 512 MiB; coverage output/cache в /tmp | **564 passed, 7 skipped**, coverage **97.76%**, минимальные 95% сохранены |
| `ruff check --no-cache app scripts tests` в том же image без сети | All checks passed |
| `pytest tests/integration/test_scoring_v2_package.py -o addopts='' -q` с RUN_SCORING_INTEGRATION=1 и локальным пакетом, без сети | **2 passed, 1 skipped** (не предоставлен исторический v1 для rollback-проверки) |
| `pytest 'tests/integration/test_real_model.py::test_real_offline_encoder_and_http[finetuned]' -o addopts='' -q`, два real-model flags, local mount, без сети | **1 passed**, настоящий encoder и HTTP rank API |
| `python -X utf8 scripts/check_cookie_https.py` с новыми backend/frontend images | **6/6 checks passed**, настоящий TLS с проверкой CA/имени |
| `scoring_stack_acceptance.py --cookie-auth --output docs/agents/artifacts/2026-10-26-pre-docs-cookie-merge/four-outcomes.json` | **passed**, четыре исхода и DB audit подтверждены |
| Разбор четырёх JSON-артефактов + проверки содержимого cases/audit | Passed |
| `git diff --cached --check`; `git diff --check` | Passed до финального staging/коммита |
| Учёт одноразовых контейнеров/томов после acceptance/TLS | **0 оставшихся task containers, 0 task volumes** |
| `docker compose config --quiet` с существующим основным .env | **Код 1**, отсутствует обязательный RECSYS_API_KEY; это отдельное ограничение локальной конфигурации |

Для HTTP-прогона заданы только переменные процесса: ML_TEST_IMAGE/BACKEND_IMAGE/FRONTEND_IMAGE с тегами `pre-docs-merge`, ML_TEST_MODEL_PATH указывает на подготовленную локальную E5, SCORING_MODEL_PATH=`/scoring-models/pre-docs-merge-scoring`, ML_TEST_HF_LOCAL_FILES_ONLY=true. Credentials создаёт harness случайно и не сохраняет в отчёте. Итоговый запуск выполнен bundled Python `C:/Users/roman/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe -X utf8`, содержащим NumPy.

### Исправленные проблемы окружения проверки

- Существующие CRLF в 21 Java-файле заменены на обязательный LF перед verify; приложение не изменилось, содержательного Git diff нет. Исходный Spotless теперь проходит в текущем checkout, а не только в отдельной копии.
- Xet-загрузка E5 давала таймауты. Обычный HTTPS работал медленно; 125829120 уже полученных последовательных байт переиспользованы, остальные диапазоны получены шестью соединениями. Две попытки с неполным/неподходящим диапазоном отклонены и повторены. Полный файл **470637416 bytes** принят только при совпадении SHA-256 `502f9765a9cebed997794d64dcdc905721d0ca7b0c47a66262f227ea42a63b4c` с закреплённым manifest. Затем штатный загрузчик проверил весь пакет и настоящий CPU smoke `[2,384]`, float32. Загрузчик приложения и правила доверия не менялись.
- Первый HTTP-прогон дошёл до проверки всех четырёх решений и аудита, но его benchmark subprocess завершился `ModuleNotFoundError: numpy` в системном Python 3.13. Повтор тем же скриптом с подготовленным bundled Python прошёл полностью. Первый запуск не выдаётся за успешный общий результат.
- Harness создаёт raw benchmark JSON в `fastapi/experiments/` даже при отдельном --output. После успешного завершения новый сгенерированный файл перенесён в игнорируемый `work/cookie-pre-docs-merge/http-benchmark.json`; его данные уже включены в основной four-outcomes.json. Исторические эксперименты не менялись.

### Границы подтверждённой работоспособности

- Проверен **HTTP/API-процесс**, в том числе через настоящий nginx и browser-cookie протокол. Браузерные клики по всему пути не проверялись. `frontend/src` не менялся в этих 45 коммитах: банковского UI и клиентских действий акцепта/подписания по-прежнему нет; для полного пути нужен API/Postman или отдельная реализация экранов.
- Скоринг действительно обученный, но демонстрационный US SBA→RU; это не новая оценка банковского качества. Обучение, изменение порогов и калибровка в этой задаче не выполнялись. Warnings об экстраполяции сохранены.
- Договор/подписание/выдача остаются синтетическими, без ЭП и движения денег. Это не реализация всех внешних проверок, залогового процесса и обслуживания из широкой reference-документации.
- Основной пользовательский stack не перезапускался, основной `.env` не изменялся. Для обычного Compose по-прежнему нужно задать RECSYS_API_KEY. Локальные модели теперь подготовлены в игнорируемой fastapi/models; проверенный тестовый стек использует собственные credentials и конфигурацию.
- Базовая E5 отдельно не скачивалась и её opt-in real-model test не запускался; проверена текущая finetuned E5. Исторический scoring v1 не скачивался. Опциональный Java `realScoringCompletesFourDecisionJourneys` ещё содержит fixture/assertions для v1 и был пропущен; текущая v2 проверена отдельным полным настоящим HTTP-harness. Адаптация этого legacy-теста не входила в merge.
- Backend/frontend images для acceptance собраны с текущими проверенными JAR/dist поверх имевшихся runtime images; полные Maven/Node build stages исходных Dockerfile отдельно не пересобирались. FastAPI runtime/test images собраны штатно полностью.

## Изменения и влияние

Входящий merge добавляет API/контракты SBA, native/HF/local загрузку закреплённого CatBoost, ScoringGateway/ScoringExchange, активную политику `data-policy-3.0-sba-annuity-1`, аудит исходной/альтернативной оценки и versioned legacy policy 2.1. Обновлены lock/dependencies, Compose, документация и ML experiments. Новых Flyway-миграций в этом merge нет: используется существующая assessment_run и credit_decision.assessment_id. Старые ревизии и история сохраняют версию политики; регрессии покрыты текущими Java-тестами.

Собственные tracked-изменения этой задачи — новый отчёт, обновлённый общий индекс и четыре санитизированных JSON в `docs/agents/artifacts/2026-10-26-pre-docs-cookie-merge/`: `four-outcomes.json`, `models.json`, `scoring-package.json`, `https-cookies.json`. Прикладной код сверх source merge не менялся. Все модели/кэши, range-download helpers, build contexts и подробные логи остаются в игнорируемых `fastapi/models/` и `work/cookie-pre-docs-merge/`. Секреты, токены и документы клиентов в tracked-артефакты не включались.

## Источники и Git

Изучены diff `1909699...1116793`, README, отчёт предыдущего merge scoring→cookie-session, `fastapi/SCORING_HF.md`, `docs/credit-scoring.md`, Java policy/gateway/assessment persistence и тесты, FastAPI routes/source/package/runner, Compose и acceptance scripts. Все результаты выше получены заново на объединённой версии; исторические результаты служили только ориентиром.

Завершение: локальный merge-коммит в `pre-docs` с родителями `190969963ebdf080bddbc7a3fceb3296e408f0fc` и `11167936d74cbe98ca552c50e3432b86cfcb60a9`, включающий этот отчёт и артефакты. Локальная `cookie-session` указывает на 1116793. Push не выполняется. До финального staging зафиксированы ожидаемые изменения merge и только новые report/artifacts плюс индекс, конфликтов нет, прикладной diff к source пуст, проверки пробелов прошли. SHA коммита и итоговая чистота дерева сообщаются в ответе после Git-проверки.
