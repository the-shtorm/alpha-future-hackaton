# Scoring: параметризуемый источник HF / локальная папка

## Запрос и границы

Пользователь попросил предварительно изучить `scoring_model`, ориентироваться на
подход `fast_api`, удалить локально поставляемые scoring-модели и использовать
публичный `thedauns/sba-scoring-v2` либо локальную папку через переменную окружения.
Работа выполнена на `scoring_model`, исходный HEAD
`c4ee30f6c81393179fe701c0f8d5b4910895018b`. Другие ветки не объединялись.
GitHub push, HF upload и публикация не выполнялись. Новый commit не создавался.

## Реализация

- `fastapi/app/scoring/source.py`: `SCORING_MODEL_PATH` принимает локальную папку,
  `file://`, короткий HF repo, HF URL или `hf://namespace/repo@<40-character SHA>/model`.
  Короткий адрес известной модели использует новый `config/scoring-hf.lock.json`;
  другой HF repo требует immutable SHA. S3 в этом загрузчике не реализован.
- HF revision: `5a0049417dae97bdc8a341c89c705d7505563645`, subfolder `model`.
  Скачиваются только manifest, CatBoost weights, calibration, domain, training,
  evaluation. Hub symlinks материализуются в отдельную атомарную папку кэша;
  native loader проверяет прежний manifest pin, hashes, версии библиотек и признаки.
- `SCORING_MODEL_PATH=thedauns/sba-scoring-v2` — default. `HF_CACHE_DIR` задаёт
  дисковый кэш, `HF_LOCAL_FILES_ONLY=true` — готовый кэш без сети. HF token
  необязателен и скрыт в Settings; для public repo проверена загрузка без токена.
  Standalone читает `fastapi/.env`, Compose — корневой `.env`.
- Scoring runner загружает один native classifier в RAM при lifespan startup.
  Inference не обращается на HF. После завершения процесса RAM освобождается,
  постоянный Docker volume сохраняет файлы для следующего запуска.
- В `encoder.py` убраны изменения глобальных HF offline environment variables,
  мешавшие загрузке скоринга после E5. Сама E5 по-прежнему загружается локально
  с `local_files_only=True`; её веса, подбор рекомендаций и пороги не менялись.
- Compose/Docker: writable `recsys_model_cache:/model-cache`, egress для HF,
  non-root и read-only root filesystem сохранены. Локальные scoring-папки доступны
  по `/scoring-models/...`, E5 отдельно по `/models/active`. Первоначальный вариант
  с пересекающимися read-only bind mounts вызвал OCI mount error и исправлен.
- CLI `scripts.prepare_scoring_model --smoke` проверяет пакет без E5 и сервера.
  Добавлены пример запроса, unit tests, opt-in native API tests, ручной CI job,
  `.env.example`, `SCORING_HF.md`, обновлены README и инструкция скоринга.
  В ручном E5 CI устранено глобальное переопределение MODEL_LOCAL_PATH,
  аналогично проверенному исправлению на cookie-session; ветка не объединялась.

## Сохранность и Git

Удалены отслеживаемые `fastapi/models/sba-scoring-v1` и `sba-scoring-v2`, исключения
для них из `.gitignore` и LFS attributes. Исходные байты перед удалением сохранены
в игнорируемом `work/scoring-model-source-backup-c4ee30f.zip`, ZIP проверен по CRC.
HF пакет v2 проверен по исходному pin. Новые snapshots/runtime caches игнорируются.
E5 LFS rules сохранены: эта задача касается только scoring. История Git не
переписывалась; старые scoring objects могут оставаться в исторических commits.
Удаления staged через `git rm`, прочие изменения до нового commit находятся
в рабочем дереве. Секретные `.env` не менялись и не добавлялись в Git.

Контрольные значения:

- `manifest.json` SHA256: `5d5498e8d3339ffbbce3d5f117f52692cee9986067a3bf6df8524c5e4c8c53ac`.
- `model.cbm`: 37,016 bytes; SHA256 `a74adc4b746381ac1396be2c7d76d1331b82e906d333412a923fc1b8bd435fb5`.
- Model `sba-scoring-v2`, feature version `sba-features-1`, calibration
  `sba-scoring-v2-sigmoid-fy2012`, operating threshold `0.167204479067272`.

## Контракты и модель

API `sba-scoring-1`, Bearer auth, девять признаков, score/probability,
calibration, warnings и Java risk/PTI rules не менялись. Локальный путь и HF
обязаны содержать тот же закреплённый пакет. Смена адреса не отключает проверки.
Существующие исторические решения БД не пересчитываются. Автоматического
fallback на v1 нет; при проблемах HF/package scoring readiness/evaluate дают 503.
В этой ветке общая readiness RecSys независима от scoring readiness.

## Выполненные проверки

1. `uv sync --frozen --python 3.11`, offline lock check: существующий lock валиден,
   зависимости и `uv.lock` не менялись. Ruff для изменённых Python файлов,
   `git diff --check` и `docker compose config --quiet` прошли.
2. Source и scoring API targeted tests: **42 passed, 1 skipped** (Windows symlinks).
3. Полный Windows pytest: **528 passed, 3 failed, 8 skipped**, coverage **99.06%**.
   Все три сбоя — исходные training fixtures/report encoding: cp1251 против UTF-8
   и символ Δ. Повтор двух затронутых модулей с `python -X utf8`: **12 passed**.
   Исследовательский training code для исправления Windows locale не менялся.
4. Полный Linux Docker suite, network none, memory 2 GiB, read-only root,
   настоящие base/finetuned E5 и native scoring из готового кэша:
   **536 passed, 3 skipped**, coverage **99.42%**, **67.61 s**.
   Для существующих Git fixture tests git установлен только в test stage.
   Legacy v1 integration требует внешнего SCORING_V1_MODEL_PATH и пропущен.
5. Свежая anonymous HF загрузка, проверка всех шести файлов и native smoke прошли.
   CLI повторён с `--local-files-only`. Дополнительная проверка TestClient:
   ровно один HF snapshot lookup и один native load при startup; четыре одинаковых
   scoring ответа, тот же объект classifier в RAM, ноль network calls на inference.
   Локальный источник дал идентичный ответ; cache-only перезапуск с заблокированной
   внешней сетью прошёл. [Результат](artifacts/2026-10-26-scoring-hf/native-source.json).
6. Собраны отдельные runtime/test Docker images, Java image и production frontend
   image. Основной пользовательский Compose stack не пересоздавался. Полный Maven
   suite в этой задаче не запускался (Java image build использовал skipTests).
7. `python -X utf8 -m scripts.scoring_stack_acceptance --source-smoke`:
   настоящий nginx frontend → Java 21 → FastAPI E5/CatBoost → PostgreSQL 17,
   **passed**. Ranking READY; DECLINED с native probability и REQUEST_INFO без
   assessment; в БД ровно одна оценка и одно связанное решение, model v2.
   Совместная HTTP нагрузка: 50 последовательных, 100 конкурентных,
   60 scoring запросов вместе с E5; ranking не изменился.
   [Полный результат](artifacts/2026-10-26-scoring-hf/java-source-smoke.json).
   После проверки временный stack и его volumes удалены.

## Измерения и оставшееся ограничение

В source-smoke FastAPI peak cgroup memory **927,096,832 bytes (~884 MiB)** вместе
с настоящей E5. Сумма пиков четырёх containers **1,315,467,264 bytes (~1.23 GiB)**.
Сумма limits 3.375 GiB + расчётный резерв ОС 2 GiB укладывается в бюджет 6 GiB;
резерв ОС не измерялся и это не длительная production-нагрузка. Scoring HTTP
p95: **33.34 ms** sequential, **67.91 ms** concurrency 4, **77.81 ms** рядом с E5.

Исторический полный four-decision journey без `--source-smoke` не прошёл:
первая fixture ожидает APPROVED по v1, но тот же исходный v2 пакет возвращает
`p=0.2525274156209339`, и Java выдаёт DECLINED. Это не ошибка HTTP-контракта или
переноса весов: standalone local/HF и Java совпадают. Финансовые правила, порог
и модель для получения ожидаемого APPROVED не менялись. Default four-outcome
fixtures требуют отдельной актуализации; source-smoke явно имеет более узкий
scope и не заявляет проверку подписания/выдачи для approved/counteroffered.

Миграция не является новой оценкой ML-качества и не изменяет demo/OOD статус
US SBA → RU. Оригинальные ограничения качества остаются в документации модели.
