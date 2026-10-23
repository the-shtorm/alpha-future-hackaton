# Умный кредитный кабинет — основа базы данных

Первая версия PostgreSQL для предпринимательских кредитов ИП/ООО. Стек: Java 21, Spring Boot 3.5.16, PostgreSQL 17; React и Nginx подключаются к будущему REST API.

В репозитории созданы **35 предметных таблиц**, четыре основные миграции Flyway, отдельная демонстрационная миграция с 15 вымышленными продуктами, описание связей и проверки целостности.

Начать изучение: [проектирование БД](docs/database-design.md), [схема связей](docs/database-erd.mmd), [контракт данных форм](docs/form-storage-contract.md).

## Что реализовано

- SQL-схема, ключи, ограничения, индексы, неизменяемые версии и история статусов.
- Разделение пользователя, компании, участников сделки и заявок.
- Версии форм, продуктов, документов, согласий, проверок и моделей.
- Основной маршрут до кредитного решения и демонстрационные договор/первая выдача/закрытие.
- Отдельные роли PostgreSQL для миграций и приложения.
- Минимальный Spring Boot bootstrap для миграций. Это пока **не REST-сервер**: контроллеры, авторизация, JPA-сущности, React и Nginx еще не реализованы.
- Отдельный контейнер FastAPI: проверка `/health`, OpenAPI и Swagger UI. Бизнес-методы и подключение Python-сервиса к БД пока не реализованы.
- Облачное развёртывание через Kubernetes, внешний PostgreSQL с TLS, отдельная Job миграций: [инструкция](docs/cloud-deployment.md).
- Автоматические тесты FastAPI с измерением покрытия, Spring Boot/Testcontainers и CI в GitHub Actions.

## Запуск в Docker

Нужен Docker с Compose и BuildKit. Java 21 и Maven устанавливаются внутри сборочного образа; устанавливать их на компьютер для этого запуска не требуется.

Из корня репозитория, если `.env` еще не создан:

```powershell
Copy-Item .env.example .env
```

Задайте в `.env` свои пароли и запустите:

```powershell
docker compose up --build -d
docker compose logs -f backend
docker compose ps -a
```

Compose поднимает PostgreSQL, дожидается успешного healthcheck и запускает Java-приложение с адресом БД `postgres:5432`. В текущей версии приложение выполняет миграции и завершает работу: **`backend Exited (0)` после успешного запуска — ожидаемый результат**. `docker ps` показывает только работающие контейнеры; завершившийся backend виден через `docker compose ps -a` или `docker ps -a`. Причина завершения — `spring.main.web-application-type: none` в `backend/src/main/resources/application.yml`. PostgreSQL, pgAdmin и FastAPI продолжают работать. REST API на Java, React и Nginx пока не реализованы, поэтому у Java-backend не опубликован HTTP-порт и не настроен постоянный перезапуск.

На Linux с SELinux каталог `infra/postgres/init` монтируется с `:ro,Z`: Docker назначает ему метку доступа текущего контейнера. Без подходящей метки PostgreSQL может завершаться с `ls: cannot open directory '/docker-entrypoint-initdb.d/': Permission denied`, из-за чего backend ожидает здоровую БД. После обновления конфигурации выполните `docker compose up -d postgres`, затем `docker compose up -d`. Удалять том `postgres_data` для этого не нужно.

Файл `.env.example` включает профиль `demo` с 15 синтетическими продуктами. Для отдельной БД без демонстрационного каталога задайте `SPRING_PROFILES_ACTIVE=`. Пароли поступают при запуске и не включаются в образ.

`Dockerfile` использует два этапа: Maven/JDK 21 для сборки и JRE 21 для запуска от непривилегированного пользователя. Сборочный контекст ограничен `backend/pom.xml` и `backend/src`: `.env`, Git, документы, кеши и локальные сборки туда не попадают. Maven-зависимости кешируются BuildKit. Интеграционные Testcontainers-тесты не запускаются внутри сборки образа; их команда приведена ниже.

Отдельно собрать образ:

```powershell
docker build -t alpha-future-backend:local .
```

После изменения исходников повторите `docker compose up --build -d backend`. Для проверки миграций передавайте runtime- и migrator-пароли, соответствующие уже созданному тому PostgreSQL; изменение `.env` само по себе пароли ролей в нем не меняет.

## FastAPI

Сервис `fastapi` собирается из каталога `fastapi/` на Python 3.13 и запускается через Uvicorn. Образ следует [официальной инструкции FastAPI для Docker](https://fastapi.tiangolo.com/deployment/docker/). Он работает от непривилегированного пользователя, с файловой системой только для чтения, healthcheck и `restart: unless-stopped`.

Чтобы собрать и запустить только FastAPI:

```powershell
docker compose up --build -d --wait fastapi
docker compose ps
Invoke-RestMethod http://localhost:8000/health
```

- Проверка процесса: [http://localhost:8000/health](http://localhost:8000/health), ответ `{"status":"ok"}`.
- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs).
- OpenAPI: [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json).

Порт доступен только на `127.0.0.1`; для изменения добавьте `FASTAPI_PORT=8001` в `.env` и пересоздайте сервис. В сети Compose адрес сервиса — `http://fastapi:8000`. FastAPI пока не обращается к PostgreSQL или Java-backend, поэтому запускается независимо от них. `/health` проверяет доступность HTTP-процесса, без проверки БД.

## Просмотр БД в pgAdmin

pgAdmin входит в Compose и доступен по адресу [http://localhost:5050](http://localhost:5050).
Он настроен по [официальной инструкции для контейнера](https://www.pgadmin.org/docs/pgadmin4/latest/container_deployment.html).
Если `.env` уже существовал, добавьте в него настройки из `.env.example`:

```dotenv
PGADMIN_PORT=5050
PGADMIN_DEFAULT_EMAIL=admin@example.com
PGADMIN_DEFAULT_PASSWORD=local-pgadmin-change-me
```

Запустить только PostgreSQL и pgAdmin без пересборки backend:

```powershell
docker compose up -d pgadmin
```

1. Откройте [http://localhost:5050](http://localhost:5050) и войдите с `PGADMIN_DEFAULT_EMAIL` и `PGADMIN_DEFAULT_PASSWORD` из `.env`.
2. Нажмите правой кнопкой на **Servers → Register → Server**. На вкладке **General** задайте имя `Credit Cabinet`.
3. На вкладке **Connection** укажите:

   | Поле | Значение |
   | --- | --- |
   | Host name/address | `postgres` |
   | Port | `5432` |
   | Maintenance database | `POSTGRES_DB` из `.env` (по умолчанию `credit_cabinet`) |
   | Username | `credit_app` |
   | Password | `DB_APP_PASSWORD` из `.env` |

4. Нажмите **Save**. Раскройте **Servers → Credit Cabinet → Databases → credit_cabinet → Schemas → credit → Tables** (если меняли `POSTGRES_DB`, выберите свое имя БД).
5. Для просмотра строк нажмите правой кнопкой на таблице: **View/Edit Data → All Rows**. Через **Tools → Query Tool** можно выполнить, например, `SELECT * FROM credit.credit_product LIMIT 100;`.

Пароль входа в pgAdmin и пароль подключения к PostgreSQL — отдельные настройки.
Для административного доступа к БД можно зарегистрировать отдельное подключение с пользователем `postgres` и паролем `POSTGRES_ADMIN_PASSWORD` из `.env`.
Внутри сети Compose используется адрес `postgres:5432`, независимо от `POSTGRES_PORT` на компьютере.
Порт pgAdmin опубликован только на `127.0.0.1`; изменить его можно через `PGADMIN_PORT`.
Настройки и учетная запись pgAdmin сохраняются в томе `pgadmin_data`. `PGADMIN_DEFAULT_EMAIL` и `PGADMIN_DEFAULT_PASSWORD` создают учетную запись при первом запуске; для существующей учетной записи меняйте пароль в интерфейсе pgAdmin.

## Запуск Java-приложения без Docker

Для запуска Java на компьютере требуются JDK 21 и Maven 3.6.3+. Сам PostgreSQL можно оставить в контейнере.

```powershell
Copy-Item .env.example .env
docker compose up -d postgres
docker compose ps
```

Значения в `.env.example` предназначены для локальной разработки. В `.env` задайте свои пароли. `.env` исключен из Git. Порт БД опубликован только на `127.0.0.1`.

Первое создание тома запускает `infra/postgres/init/001_roles.sh`: создаются `credit_migrator`, `credit_app` и схема `credit`. Изменение `.env` не меняет автоматически пароли уже созданных ролей в существующем томе. Не удаляйте том ради изменения настроек.

Для запуска bootstrap перенесите настройки из `.env` в окружение текущего PowerShell:

```powershell
Get-Content .env | Where-Object { $_ -match '^(POSTGRES_DB|POSTGRES_PORT|DB_APP_PASSWORD|DB_MIGRATOR_PASSWORD)=' } | ForEach-Object {
    $setting = $_ -split '=', 2
    [Environment]::SetEnvironmentVariable($setting[0], $setting[1], 'Process')
}
$env:DB_URL = "jdbc:postgresql://localhost:$($env:POSTGRES_PORT)/$($env:POSTGRES_DB)"
$env:SPRING_PROFILES_ACTIVE = 'demo'
mvn -f backend/pom.xml spring-boot:run
```

Профиль `demo` добавляет 15 синтетических продуктов повторяемой миграцией `R__synthetic_product_catalog.sql`. Она использует стабильные UUID и `ON CONFLICT DO NOTHING`: повторный запуск не переписывает существующие версии. Измененные условия требуют нового кода версии в исходном каталоге. Без профиля создается только схема и справочник типов документов. Используйте отдельную демонстрационную БД; включение/отключение набора миграций на одной БД требует проверки истории Flyway.

Bootstrap использует runtime-пользователя для обычного подключения и отдельного мигратора для Flyway. Hibernate настроен на `validate`, автоматическое изменение структуры отключено. Приложение работает в режиме `web-application-type: none` и пока только инициализирует инфраструктуру; HTTP endpoint нет.

## Проверки

FastAPI и облачная настройка `PORT`, включая ошибочные значения и недоступный healthcheck:

```powershell
docker compose -f compose.test.yaml run --build --rm fastapi-tests
```

Команда запускает изолированный тестовый контейнер. XML/HTML-отчёты и JUnit сохраняются в `work/test-reports/fastapi/`. Порог покрытия Python-кода с учётом ветвлений — **95%**. Рабочий образ не содержит pytest и тестовых зависимостей.

Без Docker, с Python 3.13, из каталога `fastapi`:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-test.txt
.\.venv\Scripts\python -m pytest
```

Полный интеграционный тест с контейнером PostgreSQL 17:

```powershell
mvn -f backend/pom.xml verify
```

Тесты применяют Flyway, загружают демо-каталог, проверяют 32 недопустимых действия, положительный маршрут и права runtime-роли. `CloudBootstrapTest` запускает настоящий Spring Boot main с внешним PostgreSQL и раздельными учётными записями runtime/migrator, проверяет отсутствие демо-продуктов при облачном запуске. Контейнеры одноразовые, тестовые заявки откатываются транзакцией. Нужен доступ процесса Java к Docker Engine. Отчёт JaCoCo: `backend/target/site/jacoco/index.html`; он измеряет Java-код, а SQL-инварианты проверяются интеграционными сценариями отдельно.

Workflow `.github/workflows/tests.yaml` запускает Python- и Java-тесты, сохраняет отчёты и проверяет Compose/Kubernetes-манифесты при push и pull request.

Альтернативная локальная проверка того же SQL на PostgreSQL 17.5 в WebAssembly, без Docker:

```powershell
cd tools/sql-validation
pnpm install --frozen-lockfile --ignore-scripts
pnpm test
```

Эта проверка исполняет SQL и триггеры, но не заменяет JDBC, Flyway и проверку контейнерного окружения. Проверенные результаты и ограничения среды: [validation.md](docs/validation.md).

## Структура

```text
backend/
  pom.xml
  src/main/java/ru/alphafuture/credit/CreditCabinetApplication.java
  src/main/resources/
    application.yml
    application-demo.yml
    db/migration/V1...V4__*.sql
    db/demo/R__synthetic_product_catalog.sql
  src/test/java/ru/alphafuture/credit/DatabaseIntegrityTest.java
  src/test/resources/db/database_invariants.sql
docs/
  cloud-deployment.md
  database-design.md
  database-erd.mmd
  form-storage-contract.md
  validation.md
  reference/                       # Согласованные ранее формы и кредитный путь
fastapi/
  Dockerfile
  .dockerignore
  requirements.txt
  requirements-test.txt
  pyproject.toml
  tests/
  app/__init__.py
  app/main.py
  app/settings.py
  app/server.py
  app/healthcheck.py
infra/kubernetes/
  fastapi/
  migrations/
  secret.env.example
infra/postgres/init/001_roles.sh
tools/build_demo_catalog.py
tools/sql-validation/
Dockerfile
.dockerignore
.gitattributes
compose.yaml
compose.test.yaml
.github/workflows/tests.yaml
.env.example
```

Продукты, подписи, внешние проверки и выдачи в демо не являются реальными банковскими операциями. Формула нечеткой логики здесь не определяется.
