# Развёртывание в облаке

Подготовлен переносимый вариант для Kubernetes: каталог `infra/kubernetes/fastapi` содержит Deployment с двумя репликами и внутренний Service, `infra/kubernetes/migrations` — отдельную одноразовую Job для Java/Flyway. Его можно адаптировать к управляемому Kubernetes выбранного облака. Создание кластера, PostgreSQL, registry, домена и облачных IAM-ролей выполняется в аккаунте провайдера; эти ресурсы и реальные реквизиты в репозиторий не включены. Фактическое развёртывание в облаке ещё не проверено.

FastAPI поддерживает переменную `PORT` (по умолчанию `8000`) и слушает `0.0.0.0`. Контейнер можно использовать и на контейнерной платформе без Kubernetes, если она запускает Linux-образы и передаёт порт через `PORT`. Команда запуска — `python -m app.server`; переменная не должна быть пустой, допустимы числа 1–65535. Docker healthcheck использует тот же порт. Это поддержка контейнерного запуска, без отдельных Terraform-модулей для провайдеров.

## Подготовка образов

Войдите в выбранный registry способом, предусмотренным вашим облаком. Из корня репозитория:

```powershell
$registry = 'registry.example.com/credit-cabinet'
$release = 'v0.1.0'
docker build -t "${registry}/backend:${release}" .
docker build -t "${registry}/fastapi:${release}" ./fastapi
docker push "${registry}/backend:${release}"
docker push "${registry}/fastapi:${release}"
```

В обоих `kustomization.yaml` замените `images[].newName` и `newTag` на опубликованные имена и тег релиза. Для закрытого registry настройте доступ узлов через IAM провайдера либо `imagePullSecrets` в Pod templates. Registry и тег из примера являются заполнителями.

## Внешний PostgreSQL

Создайте PostgreSQL 17 и базу `credit_cabinet`, разрешите сетевой доступ из кластера. На новой БД администратор должен создать роли `credit_migrator`, `credit_app` и схему `credit` с владельцем `credit_migrator`, отозвать `CREATE` у `PUBLIC` в схеме `public`, выдать приложению `USAGE` на `credit`. Точные SQL-команды находятся в `infra/postgres/init/001_roles.sh`. Миграции выполняются от отдельного владельца схемы; приложению не нужны административные права. Существующую БД и роли повторно не инициализируйте.

Получите корневой сертификат PostgreSQL у провайдера и сохраните локально как `work/cloud/postgres-ca.crt`. В `DB_URL` используется `sslmode=verify-full` и путь к сертификату внутри Pod; hostname должен совпадать с сертификатом. Не отключайте проверку TLS для обхода ошибки сертификата.

```powershell
kubectl create namespace credit-cabinet
kubectl -n credit-cabinet create configmap postgres-ca --from-file=ca.crt=work/cloud/postgres-ca.crt
Copy-Item infra/kubernetes/secret.env.example infra/kubernetes/secret.env
```

Заполните `secret.env` адресом БД и реальными паролями. Файл исключён из Git. Создайте Secret:

```powershell
kubectl -n credit-cabinet create secret generic database --from-env-file=infra/kubernetes/secret.env
```

В рабочем облаке можно вместо файла использовать интеграцию Secret Manager провайдера, создающую Secret `database` с теми же ключами. FastAPI пока не использует БД и не получает эти пароли.

## Миграции и запуск

Проверьте выбранный контекст `kubectl config current-context`. Java-приложение выполняет миграции и завершается, поэтому используется [Job](https://kubernetes.io/docs/concepts/workloads/controllers/job/). Демо-каталог в облачной Job отключён.

```powershell
kubectl apply -k infra/kubernetes/migrations
kubectl -n credit-cabinet wait --for=condition=complete job/backend-migrations --timeout=300s
kubectl -n credit-cabinet logs job/backend-migrations
```

Продолжайте только после успешного завершения Job. Для следующего релиза дождитесь завершения предыдущей миграции, обновите тег образа, удалите только завершённую Job командой `kubectl -n credit-cabinet delete job backend-migrations` и повторите запуск. Манифесты Job нельзя обновлять на месте при изменении образа. Схему и данные БД эта команда не удаляет.

```powershell
kubectl apply -k infra/kubernetes/fastapi
kubectl -n credit-cabinet rollout status deployment/fastapi --timeout=180s
kubectl -n credit-cabinet port-forward service/fastapi 8000:80
```

Во втором терминале проверьте `Invoke-RestMethod http://localhost:8000/health`. Для публичного адреса подключите Service к Ingress/HTTPS-балансировщику своего облака и настройте домен с сертификатом. По умолчанию сервис внутренний и не создаёт платный публичный LoadBalancer. Публичный бизнес-API и авторизация пока не реализованы.

В Deployment настроены [startup/readiness/liveness probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/), ограничения CPU/памяти и запуск от UID 10001 с файловой системой только для чтения. `/health` проверяет процесс FastAPI, без проверки PostgreSQL. Миграции и FastAPI развёртываются отдельными командами; Kubernetes не задаёт между ними порядок автоматически.

## Проверка без облака

```powershell
kubectl kustomize infra/kubernetes/fastapi
kubectl kustomize infra/kubernetes/migrations
docker compose -f compose.test.yaml run --build --rm fastapi-tests
```

CI дополнительно проверяет собранные манифесты по Kubernetes JSON Schema через kubeconform. Это не заменяет пробный запуск в конкретном кластере с его сетевыми правилами и admission policies.
