# Проверка cookie-session: frontend, Java и FastAPI/RecSys

Дата: 26 октября 2026 года. Проверяемая версия: cookie-session, commit 2e88bd9.
База сравнения: fast_api, commit 8fa96cd. Запрос — проверить интеграцию после
изменений команды и кратко перечислить проблемы. Код приложения не исправлялся.

## Изоляция проверки

На старте рабочий каталог был чистым и находился на cookie-session. Во время
проверки в нём началось постороннее слияние. По прямому указанию пользователя
scoring_model исключена из рассмотрения; её конфликты и файлы не исправлялись.
Проверка продолжена на отдельном git archive 2e88bd9 в
work/cookie-session-review-2e88bd9. Сборки, тесты и этот отчёт относятся только
к зафиксированному коммиту cookie-session, а не к незавершённому слиянию.
Рабочие контейнеры и production image tags не заменялись. Индекс отчётов
обновляется только в изолированной копии, без правки текущего merge.

## Совместимость

Diff с fast_api подтверждает отсутствие изменений fastapi/app, DTO/OpenAPI,
конфигураций модели/порогов, uv.lock, RecsysGateway, AutomaticSelection и
RankingExchange. Из ML-кода изменён только scripts/java_acceptance.py:
стандартная библиотека вместо импорта Pydantic для чтения model lock и более
полная проверка saved selection/product choice/application draft.

Cookie/CSRF относится к browser -> Java. Внутренний Java -> FastAPI запрос
сохранил отдельный Bearer API key и контракт /api/v1/recommendations/rank-java.
nginx /api маршрутизирует запросы в Java; секрет ML не передаётся frontend.
Legacy /auth/login Bearer API сохранён наряду с /auth/session cookie API.
SESSION_COOKIE_SECURE=false используется только для локального HTTP acceptance;
для production HTTPS необходим true, как указано в документации команды.

Frontend api.ts использует same-origin credentials, получает CSRF через Java,
отправляет header для мутаций и ограниченно повторяет только CSRF_INVALID.
Обычные сетевые ошибки не приводят к повторному выполнению мутаций. Autosave
передаёт rowVersion, а выбор продукта/черновик используют сохранённый profile.
Рендер рекомендаций сохраняет все candidates и читает isRecommended из backend.
Для нуля рекомендаций исправлен текст summary: он больше не обещает выделенные
предложения, если ни один флаг не установлен.

## Подтверждённая проблема: ручной real-java CI

P2, унаследовано из fast_api, не появилось из-за cookie-session:
.github/workflows/recsys-tests.yaml:90 передаёт MODEL_LOCAL_PATH=/models/...
глобально всему pytest-процессу. tests/unit/test_finetuned_runtime.py:21 ожидает
нетронутый default path, но Settings читает эту переменную. Поэтому ручная job
в шаге Real offline tests in Linux получает AssertionError независимо от
исправности самой модели.

Первый Linux-прогон с таким окружением воспроизвёл ровно это: 202 passed,
1 failed (default runtime path). Обе настоящие модели и HTTP при этом прошли.
После удаления MODEL_LOCAL_PATH и монтирования моделей в стандартные /app/models
пути полный прогон дал 203 passed. Рекомендуемое исправление CI — такой же mount
без глобального переопределения либо явная изоляция env в default-config тесте.
В рамках review workflow/test source не менялись.

## Фактические проверки

- FastAPI test и runtime images из snapshot: сборка с uv sync --frozen успешна.
- Java backend image из snapshot: Maven package/компиляция успешны; этот build
  использует -DskipTests. Полный Java Maven/Testcontainers suite заново не запускался.
- Frontend production image: TypeScript + Vite build успешны.
- Frontend npm test в Node 22 image, без сети: все 33 теста успешны
  (12 form, 10 API/session/view, 11 draft).
- FastAPI полный pytest в Linux, network none, read-only root, limit 2 GiB,
  обе настоящие E5: 203 passed, coverage 98.01%, без пропусков. Ruff check успешен.
- Временный Compose project с Java/PostgreSQL/FastAPI/frontend использует отдельные
  image tags cookie-review-2e88bd9, случайные секреты и собственный новый том БД.
- Реальный HTTP через nginx /api с cookie/CSRF прошёл весь расширенный
  scripts.java_acceptance: conditional, unknown_context, logistics -> READY,
  четыре кандидата и три рекомендации; empty -> EMPTY, ноль кандидатов.
- Проверены saved selections/view, выбор продукта, создание/чтение draft с
  сохранённой суммой, idempotent import/retry, stale import -> 409.
- Cookie login не вернул accessToken в JSON, HttpOnly session cookie получена,
  /me доступен; login/logout без CSRF отвергнуты 403, logout инвалидировал /me
  до 401. Прямой FastAPI model-info без внутреннего ключа отвергнут 401.
- Cookie test сохраняет legacy Bearer login и использует внутренний Bearer при
  прямых ML-запросах. Это проверяет оба механизма без смешивания credentials.
- Model ID, artifact SHA 116acca8c00237091e511ea6e96a2959ad1345d9439b8c5a9c7fc2c29b9012e8
  и maxCosineDistance 0.5237781852483749 совпали с действующими lock/policy.
- Нулевой порог в отдельном тестовом стеке: все четыре сценария успешны; непустые
  выдачи сохранили по четыре кандидата с нулём рекомендаций. Через cookie/CSRF
  по-прежнему работают выбор продукта, черновик, повторный импорт и stale checks.

## Сохранившиеся ограничения

Новых критических несовместимостей cookie-session с RecSys в проверенной цепочке
не обнаружено. Кроме подтверждённого CI-дефекта остаются прежние ограничения:

- Очередь из четырёх холодных запросов по 100 кандидатов в прошлом измерении
  занимала до 14.89 с при максимальном timeout Java 10 с. Модель/runner/gateway
  здесь не изменены; новая нагрузочная проверка этого предела не выполнялась.
- Строгий бюджет всего сервера 6 ГБ ещё не принят: только ML имеет memory cap;
  review не меняет лимиты остальных контейнеров и не проверяет RAM всей машины.
- Это HTTP-level integration через настоящий nginx, не новая ручная браузерная
  проверка всех UI-переходов. HTTPS-cookie/TLS проверка в этой задаче не повторялась.
- Модель и policy не переобучались; качество на неподтверждённых синтетических
  метках не становится подтверждённым вследствие успешной интеграции.
- HF download path/manifest/cache настройки не изменились. В этом review E5
  запускалась на read-only локальных весах; холодный download HF не повторялся.

## Артефакты и Git

В snapshot/work/: cookie-chain-default.json и cookie-chain-default-cookie.json,
cookie-chain-zero.json и cookie-chain-zero-cookie.json.
Harness review_cookie_chain.py адаптирует существующий acceptance через временный
nginx/cookie override; application source и базовый Compose не редактируются.
Временные стеки удаляются самим acceptance, включая только собственные тома.
Секреты не выводились. Commit, push, переключение ветки и разрешение чужого merge
агентом не выполнялись. Отчёт и доказательства остаются в изолированной review-копии.

## Сохранение отчёта в основной репозиторий

По последующему запросу пользователя отчёт и четыре JSON-доказательства перенесены
в основной docs/agents/ на cookie-session. Сам snapshot сохранён. Указанный выше
CI-дефект исправляется отдельной задачей; см. [отчёт исправления](2026-10-26-cookie-session-ci-model-path-fix.md).

- [cookie-chain-default.json](artifacts/2026-10-26-cookie-session-recsys-review/cookie-chain-default.json)
- [cookie-chain-default-cookie.json](artifacts/2026-10-26-cookie-session-recsys-review/cookie-chain-default-cookie.json)
- [cookie-chain-zero.json](artifacts/2026-10-26-cookie-session-recsys-review/cookie-chain-zero.json)
- [cookie-chain-zero-cookie.json](artifacts/2026-10-26-cookie-session-recsys-review/cookie-chain-zero-cookie.json)
