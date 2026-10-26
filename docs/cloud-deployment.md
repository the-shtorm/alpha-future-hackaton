# Облачная инфраструктура и шаблоны Kubernetes

[Документация проекта](README.md) · [Локальная демонстрация](hackathon-start.md)

Каталог `infra/kubernetes/` содержит вошедшие из `db-init` шаблоны размещения
FastAPI и отдельной миграционной Job. Kustomize объединяет ресурсы и подставляет
имена образов. Параметры конкретного кластера задаются перед применением:
registry, версии образов, Secret, ConfigMap, модельные пакеты, ресурсы и сеть.

## Состав шаблонов

| Каталог | Ресурсы |
|---|---|
| `infra/kubernetes/fastapi` | Deployment с двумя репликами и Service типа ClusterIP, 80 → именованный порт http |
| `infra/kubernetes/migrations` | Job backend-migrations, restartPolicy Never, backoffLimit 1, activeDeadlineSeconds 300 |
| `infra/kubernetes/secret.env.example` | Пример реквизитов внешнего PostgreSQL с TLS и разделёнными ролями |

Namespace обоих Kustomization — `credit-cabinet`. В `images` замените
`registry.example.com/...` и `replace-with-release-tag` на registry и тег релиза.
Для закрытого registry настройте доступ узлов либо `imagePullSecrets`.

## Подготовка приложения и моделей

Для повторяемого релиза используйте образы из одного commit. Java-приложение
запускает HTTP API и Flyway при старте. FastAPI использует Python 3.11, E5 и SBA;
поддерживает `PORT` и слушает `0.0.0.0`. Штатная команда — `python -m app.server`.

Перед развёртыванием FastAPI задайте в окружении Pod:

- `ML_INTERNAL_API_KEY` из Secret; тот же ключ используется Java.
- `MODEL_VARIANT=finetuned`, `MODEL_PATH` с закреплённым источником E5.
- `SCORING_ENABLED=true`, `SCORING_MODEL_PATH=thedauns/sba-scoring-v2`.
- Writable-кэш `/model-cache` и переменные `HF_CACHE_DIR`, `HF_HOME`, `HF_XET_CACHE`.
- Доступ к источникам пакетов; `HF_TOKEN` из Secret для источника, требующего токен.

Имена и значения закреплённых пакетов: [MODEL_HANDOFF](../fastapi/MODEL_HANDOFF.md),
[SCORING_HF](../fastapi/SCORING_HF.md), [конфигурация](configuration.md).
Для каждого Pod предусмотрите доступный кэш и ресурсы загрузки/inference модели.
Штатный Compose задаёт FastAPI лимит 2 ГБ; requests/limits в Kubernetes
подбираются под выбранный образ и нагрузку. Startup probe учитывает время
подготовки пакета, readiness использует `/health/ready`, liveness — `/health/live`.
SBA дополнительно предоставляет внутренний `/api/v1/scoring/ready`.

В поставленном шаблоне probes указывают на `/health`. Перед применением релизной
конфигурации установите нужные пути и интервалы для текущего ML-runtime.

## Внешний PostgreSQL и миграции

Подготовьте PostgreSQL 17 и БД `credit_cabinet`, сетевой доступ из кластера,
роли `credit_migrator`, `credit_app` и схему `credit` с владельцем миграций.
Исходные SQL-команды находятся в `infra/postgres/init/001_roles.sh`.
Для существующей БД используются её роли и схема.

Сертификат CA PostgreSQL монтируется через ConfigMap `postgres-ca` в
`/etc/postgresql/ca.crt`. В JDBC URL задаются `sslmode=verify-full` и
`sslrootcert`; hostname соответствует сертификату. Secret `database`
содержит ключи из `infra/kubernetes/secret.env.example`. Рабочий файл
`infra/kubernetes/secret.env` исключён из Git.

Шаблон `backend-migrations` предназначен для однократного миграционного шага.
Подставьте миграционный образ либо команду, выполняющую Flyway и завершающуюся
с exit code 0 после успешного применения схемы. Обычный backend-образ
обслуживает HTTP и продолжает работу после стартовых миграций; для Job
нужно явно выбрать завершаемый миграционный entrypoint. Demo-профиль в Job
отключён. Демо-каталог и учётные записи настраиваются для экземпляра приложения.

## Порядок применения подготовленной конфигурации

1. Опубликуйте образы релиза в выбранный registry и обновите оба Kustomization.
2. Настройте namespace, доступ к registry, Secret, CA и модельное хранилище.
3. Подготовьте команду миграций и параметры ML-runtime, описанные выше.
4. Примените миграционный шаг, дождитесь успешного завершения.
5. Примените Deployment/Service FastAPI и дождитесь readiness.
6. Настройте размещение Java API, frontend, PostgreSQL и хранилища документов,
   маршрутизацию Java → FastAPI и frontend → Java.
7. Подключите frontend и `/api` через единый origin с HTTPS; задайте
   `SESSION_COOKIE_SECURE=true`. Настройте внешний маршрут в инфраструктуре кластера.

Команды для уже настроенных шаблонов:

```sh
kubectl apply -k infra/kubernetes/migrations
kubectl -n credit-cabinet wait --for=condition=complete job/backend-migrations --timeout=300s
kubectl apply -k infra/kubernetes/fastapi
kubectl -n credit-cabinet rollout status deployment/fastapi --timeout=600s
```

В следующем релизе после завершения предыдущей Job создаётся новый миграционный
запуск по правилам выбранного deployment-процесса. Данные БД хранятся отдельно
от жизненного цикла Job и Pod приложения.

## Параметры доступа и изоляции

Шаблоны используют UID/GID 10001, read-only root filesystem, запрет повышения
привилегий, drop ALL capabilities, seccomp RuntimeDefault, отключённый автоматический
service-account token и отдельный tmpfs. Service FastAPI остаётся внутренним;
клиентский браузер обращается к Java через `/api` frontend.

Локальная полная демонстрация выполняется по [Docker-инструкции](hackathon-start.md).
В `docs/validation.md` перечислены подготовленные команды проверок, а результаты
конкретных запусков фиксируются отдельно в отчётах задач.
