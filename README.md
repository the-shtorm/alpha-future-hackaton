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

Compose поднимает PostgreSQL, дожидается успешного healthcheck и запускает Java-приложение с адресом БД `postgres:5432`. В текущей версии приложение выполняет миграции и завершает работу: **`backend Exited (0)` после успешного запуска — ожидаемый результат**. PostgreSQL продолжает работать. HTTP API, React и Nginx пока не реализованы, поэтому у backend не опубликован HTTP-порт и не настроен постоянный перезапуск.

Файл `.env.example` включает профиль `demo` с 15 синтетическими продуктами. Для отдельной БД без демонстрационного каталога задайте `SPRING_PROFILES_ACTIVE=`. Пароли поступают при запуске и не включаются в образ.

`Dockerfile` использует два этапа: Maven/JDK 21 для сборки и JRE 21 для запуска от непривилегированного пользователя. Сборочный контекст ограничен `backend/pom.xml` и `backend/src`: `.env`, Git, документы, кеши и локальные сборки туда не попадают. Maven-зависимости кешируются BuildKit. Интеграционные Testcontainers-тесты не запускаются внутри сборки образа; их команда приведена ниже.

Отдельно собрать образ:

```powershell
docker build -t alpha-future-backend:local .
```

После изменения исходников повторите `docker compose up --build -d backend`. Для проверки миграций передавайте runtime- и migrator-пароли, соответствующие уже созданному тому PostgreSQL; изменение `.env` само по себе пароли ролей в нем не меняет.

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

Полный интеграционный тест с контейнером PostgreSQL 17:

```powershell
mvn -f backend/pom.xml test
```

Тесты применяют Flyway, загружают демо-каталог, проверяют 32 недопустимых действия, положительный маршрут и права runtime-роли. Контейнер одноразовый, тестовые заявки откатываются транзакцией. Нужен доступ процесса Java к Docker Engine.

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
  database-design.md
  database-erd.mmd
  form-storage-contract.md
  validation.md
  reference/                       # Согласованные ранее формы и кредитный путь
infra/postgres/init/001_roles.sh
tools/build_demo_catalog.py
tools/sql-validation/
Dockerfile
.dockerignore
.gitattributes
compose.yaml
.env.example
```

Продукты, подписи, внешние проверки и выдачи в демо не являются реальными банковскими операциями. Формула нечеткой логики здесь не определяется.
