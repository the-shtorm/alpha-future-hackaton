# Сторонние компоненты, модели, датасеты и сервисы (THIRD_PARTY_NOTICES)

Файл фиксирует внешние компоненты, модели, датасеты и сервисы, используемые
демонстрационным проектом «Кредитный кабинет для бизнеса» (хакатон), а также
перечень смоделированных интеграций. Версии взяты из манифестов проекта:
`backend/pom.xml`, `frontend/package.json`, `fastapi/pyproject.toml`,
`fastapi/requirements.txt`, `compose.yaml` и lock-файлов `fastapi/config/`.

## Backend — Java 21, Spring Boot

| Компонент | Версия | Назначение | Лицензия |
|---|---|---|---|
| Spring Boot (starter-parent; web, security, jdbc, validation, test) | 3.5.16 | REST API, безопасность, доступ к БД | Apache-2.0 |
| springdoc-openapi-starter-webmvc-ui | 2.8.17 | Swagger UI и OpenAPI | Apache-2.0 |
| Flyway (flyway-core, flyway-database-postgresql) | в составе Spring Boot BOM | Миграции схемы БД | Apache-2.0 |
| PostgreSQL JDBC driver | в составе Spring Boot BOM | Доступ к PostgreSQL | BSD-2-Clause |
| Testcontainers (postgresql, junit-jupiter), spring-boot-testcontainers, spring-security-test | тестовый scope | Интеграционные тесты | MIT / Apache-2.0 |
| JaCoCo | 0.8.15 | Покрытие тестами | EPL-2.0 |
| Spotless + google-java-format | 3.10.4 / 1.33.0 | Форматирование исходников (стиль AOSP) | Apache-2.0 |
| maven-javadoc-plugin | 3.6.3 | Сборка Javadoc | Apache-2.0 |

## Frontend — React, Vite

| Компонент | Версия | Назначение | Лицензия |
|---|---|---|---|
| react, react-dom | 19.2.0 | UI-библиотека | MIT |
| @alfalab/core-components-{config, stack-context, button, input, textarea, vars} | см. `frontend/package.json` | Компоненты Alfa Design System (Альфа-Банк) | MIT |
| Vite, @vitejs/plugin-react | 7.1.12 / 5.0.4 | Сборка и dev-сервер | MIT |
| TypeScript | 5.9.3 | Типизация | Apache-2.0 |
| @types/node, @types/react, @types/react-dom | dev-зависимости | Определения типов | MIT |

## ML-сервис — FastAPI, Python 3.11

| Компонент | Версия | Назначение | Лицензия |
|---|---|---|---|
| FastAPI, Uvicorn | закреплены `fastapi/requirements.txt` и `uv.lock` | HTTP-сервис ML | MIT / BSD-3-Clause |
| Pydantic, pydantic-settings | 2.x | Модели данных и настройки | MIT |
| sentence-transformers, transformers | transformers 5.20.2 | Инференс E5-эмбеддингов | Apache-2.0 |
| huggingface-hub | см. `requirements.txt` | Загрузка закреплённых ревизий моделей | Apache-2.0 |
| PyTorch (CPU-сборка `2.14.1+cpu`, индекс `download.pytorch.org/whl/cpu`) | 2.14.1+cpu | Вычисления E5 | BSD-3-Clause |
| CatBoost | 1.2.10 | Модель кредитного риска SBA | Apache-2.0 |
| pandas | 2.3.3 | Подготовка данных | BSD-3-Clause |
| scikit-learn | 1.9.1 | Метрики и валидация обучения | BSD-3-Clause |
| NumPy | см. `requirements.txt` | Числовые вычисления | BSD-3-Clause |
| boto3 / botocore | 1.43.x | Доступ к S3-совместимому хранилищу артефактов | Apache-2.0 |
| pytest, pytest-cov, httpx, jsonschema, ruff | dev-группа `pyproject.toml` | Тесты и линт | MIT / MIT / BSD-2-Clause / MIT / MIT |

## Инфраструктура и Docker-образы

| Компонент | Версия/тег | Назначение | Лицензия |
|---|---|---|---|
| postgres | `postgres:17-bookworm` | СУБД PostgreSQL 17 | PostgreSQL License |
| pgAdmin 4 | `dpage/pgadmin4:9.18` | Администрирование БД (демо) | PostgreSQL Licence |
| nginx (unprivileged) | `nginxinc/nginx-unprivileged:1.28-alpine` | Раздача frontend | BSD-2-Clause |
| Node.js | `node:22-alpine` | Сборка frontend | MIT |
| Eclipse Temurin (JDK/JRE) | `maven:3.9-eclipse-temurin-21`, `eclipse-temurin:21-jre-jammy` | Сборка и запуск backend | GPLv2 + Classpath Exception |
| Python | `python:3.11-slim-bookworm` | ML-сервис | PSF |
| uv | `ghcr.io/astral-sh/uv:0.10.2` | Установка Python-зависимостей | Apache-2.0 / MIT |
| Kubernetes API, Kustomize, GitHub Actions | — | Шаблоны развёртывания и CI | Apache-2.0 |

## Модели

| Модель | Назначение | Источник | Происхождение/права | Закрепление |
|---|---|---|---|---|
| `intfloat/multilingual-e5-small` | Базовая модель семантического ранжирования запроса и продукта | Hugging Face Hub | Публичная модель Intfloat, лицензия MIT (см. карточку модели) | revision `614241f622f53c4eeff9890bdc4f31cfecc418b3` (`fastapi/config/model.lock.json`) |
| `e5-credit-finetune-v1` (HF-репозиторий `thedauns/e5-credit-finetune-v1`, приватный) | Дообученная E5 для кредитных запросов; используется в runtime | Hugging Face Hub (приватный репозиторий команды) | Создана командой проекта дообучением базовой E5; производная от `intfloat/multilingual-e5-small` | SHA-256 артефакта `116acca8…` (`fastapi/config/finetuned-model.lock.json`, `hf-deployment.lock.json`) |
| `sba-scoring-v2` (HF-репозиторий `thedauns/sba-scoring-v2`) | CatBoost-оценка вероятности списания по займу | Hugging Face Hub | Обучена командой проекта на датасете SBA (см. ниже) | manifest SHA-256 `5d5498e8…` (`fastapi/config/scoring-model.lock.json`, `scoring-hf.lock.json`) |

## Датасеты

| Датасет | Назначение | Происхождение/права | Закрепление |
|---|---|---|---|
| `sba_dataset(2010-2026).csv` (461 559 строк, 23 колонки; цель `LoanStatus`, 1 — списание/CHGOFF) | Обучение и оценка модели `sba-scoring-v2` | Публичные данные кредитов U.S. Small Business Administration (SBA), правительственные данные США (public domain) | SHA-256 `eb9efbe8…` (`fastapi/scoring_training/config/dataset.lock.json`); исходный CSV не входит в Git (`data/scoring/raw/`) |
| Синтетический каталог из 15 кредитных продуктов с версиями условий | Демонстрация подбора продукта | Создан командой хакатона; реальных продуктов банков не содержит | `docs/reference/products-demo.json` и сиды БД |
| Учебные данные демонстрационного контура (демо-аккаунты `demo-owner`/`demo-bank`, учебный макроконтекст, демо-документ `docs/demo/sample-document.pdf`, примеры в `docs/reference/`, `docs/contracts/`) | Демонстрация сценариев | Созданы командой хакатона | Зафиксированы в документации и миграциях |

## Сервисы и внешние площадки

- **Hugging Face Hub** — загрузка закреплённых ревизий моделей при сборке/запуске
  (`intfloat/multilingual-e5-small`, приватный `thedauns/e5-credit-finetune-v1`,
  `thedauns/sba-scoring-v2`). Для приватного репозитория требуется токен.
- **S3-совместимое объектное хранилище** (доступ через `boto3`) — опциональный
  источник ML-артефактов.
- **GitHub** — хостинг репозитория и CI (workflows `.github/workflows/tests.yaml`,
  `.github/workflows/recsys-tests.yaml`).
- **Демонстрационный стенд** `http://77.91.93.166:3000` — размещён командой
  хакатона, сторонним сервисом не является.

## Смоделированные (имитируемые) интеграции

Проект работает в демонстрационном контуре. Перечисленные шаги выглядят как
интеграции с внешними системами, но смоделированы внутри приложения и не
обращаются к реальным банковским, государственным и финансовым системам:

- **Выдача кредита** — «учебная выдача» и подтверждение «демонстрационного
  договора»: платёжные системы и бухгалтерские шлюзы банка не подключаются,
  денежные переводы не выполняются.
- **Кредитное решение и скоринг** — вероятность списания оценивает CatBoost
  `sba-scoring-v2`, обученная на данных SBA (американский портфель кредитов);
  Java-слой комбинирует её с параметрами сделки и финансовой политикой проекта.
  Результат — демонстрационная оценка, а не реальное кредитное решение.
- **Бюро кредитных историй** (БКИ/НБКИ/ОКБ) и внешние скоринговые бюро не
  подключаются; кредитная история заёмщика не запрашивается.
- **Государственные реестры и сервисы** (ФНС/ЕГРЮЛ, Госуслуги и аналоги) не
  подключаются; проверки выполняются в интерфейсе на демо-данных.
- **Проверка документов** — «банковская проверка» выполняется сотрудником в
  кабинете; автоматической верификации подлинности документов нет.
- **Макроэкономический контекст** — «учебный макроконтекст» вводится вручную для
  демонстрации; подключённых источников макроданных (ЦБ, биржи) нет.
- **Каталог кредитных продуктов** синтетический и не является офертой реального
  банка; названия и условия вымышлены.

## Примечания

- Лицензии указаны по данным upstream-проектов и полю `license` пакетов;
  юридически значимыми являются оригинальные лицензионные тексты в составе
  дистрибутивов соответствующих компонентов.
- У репозитория проекта на момент подготовки файла собственная лицензия не
  заявлена; перечень носит информационный характер для проверяющих хакатона.
- Точные runtime-версии закреплены в `fastapi/requirements.txt` (хеши из
  `uv.lock`), `frontend/package-lock.json`, `backend/pom.xml`; версии моделей и
  датасета — в lock-файлах `fastapi/config/` и
  `fastapi/scoring_training/config/dataset.lock.json`.
