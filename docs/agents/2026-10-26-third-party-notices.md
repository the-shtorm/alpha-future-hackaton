# THIRD_PARTY_NOTICES: перечень сторонних компонентов

Дата: 2026-10-26. Статус: завершена.

## Запрос

Пользователь запросил добавить файл `THIRD_PARTY_NOTICES` с перечнем используемых
сторонних компонентов, моделей, датасетов и сервисов, а также указанием
смоделированных интеграций. Ранее запланированные задачи (push main на GitHub,
проверка ссылок README) пользователь явно отменил формулировкой «просто добавьте
файл».

## Изменения

- Создан `THIRD_PARTY_NOTICES.md` в корне репозитория (расширение `.md` выбрано
  для рендеринга на GitHub; имя сути запроса сохранено). Разделы: Backend (Java/
  Spring Boot по `backend/pom.xml`), Frontend (React/Vite по
  `frontend/package.json`), ML-сервис (FastAPI по `fastapi/pyproject.toml` и
  `requirements.txt`), Docker-образы (по `compose.yaml` и Dockerfile), модели,
  датасеты, сервисы/площадки, смоделированные интеграции, примечания.
- Создан этот отчёт; добавлена строка в `docs/agents/log.md`.

## Источники

`backend/pom.xml`, `frontend/package.json`, `fastapi/pyproject.toml`,
`fastapi/requirements.txt`, `compose.yaml`, Dockerfile (backend/frontend/fastapi),
`fastapi/config/{model,finetuned-model,hf-deployment,scoring-model,scoring-hf}.lock.json`,
`fastapi/scoring_training/config/dataset.lock.json`, `data/scoring/README.md`,
`fastapi/scoring_training/README.md`, `frontend/README.md`, `README.md`,
`docs/README.md`, `docs/demo/`, `docs/reference/products-demo.json`.

Зафиксировано фактическое: E5-база `intfloat/multilingual-e5-small` (rev
`614241f6…`), дообученная `e5-credit-finetune-v1` (HF `thedauns/e5-credit-finetune-v1`,
приватный, SHA-256 `116acca8…`), CatBoost `sba-scoring-v2` (HF
`thedauns/sba-scoring-v2`, manifest `5d5498e8…`), датасет SBA
`sba_dataset(2010-2026).csv` (461 559 строк, SHA-256 `eb9efbe8…`), образы
`postgres:17-bookworm`, `dpage/pgadmin4:9.18`, `nginxinc/nginx-unprivileged:1.28-alpine`
и др. Лицензии указаны по upstream-данным и полю `license` пакетов
(проверено непосредственно для `@alfalab/core-components-button` — MIT).

## Смоделированные интеграции (по README и документации)

Учебная выдача и демонстрационный договор, демо-скоринг на данных SBA без БКИ,
проверка документов в интерфейсе без ФНС/Госуслуг, ручной учебный макроконтекст
без источников макроданных, синтетический каталог продуктов.

## Верификация

Тесты и сборки не запускались — задача документационная. Проверено повторным
чтением файла: разделы и таблицы на месте, ссылки на lock-файлы соответствуют
реальным путям в репозитории. Git: изменения не закоммичены (рабочее дерево
содержало незакоммиченные правки README/docs от предыдущей задачи; push main
не выполнялся по отменённому запросу).

## Ограничения

- Лицензии приведены справочно; юридически значимы оригинальные тексты upstream.
- Точные версии части транзитивных Python-зависимостей смотреть в
  `fastapi/requirements.txt`/`uv.lock`; в файле перечислены прямые компоненты.
- Собственная лицензия репозитория не заявлена (LICENSE отсутствует).
