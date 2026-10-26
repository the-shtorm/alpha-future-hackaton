# Воспроизводимые проверки проекта

[Навигация](README.md) · [Сценарий для проверяющего](hackathon-start.md)

## Штатный Docker-запуск

Из корня репозитория:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start-demo.ps1
```

Либо Linux/macOS:

```sh
bash scripts/start-demo.sh
```

Скрипт подготавливает `.env`, собирает образы и вызывает
`docker compose up --build --detach --wait --wait-timeout 2400`.
Readiness FastAPI включает загрузку моделей, frontend проверяет `/api/health`
через Java и PostgreSQL. После готовности откройте `http://localhost:3000`.

Минимальная приёмка: войти клиентом, заполнить форму, получить E5-подбор,
выбрать продукт, создать и дополнить заявку, загрузить PDF, отправить её;
в отдельной банковской сессии сохранить макроконтекст, назначить заявку,
подтвердить файлы и запустить скоринг; клиентом принять условия и подписать
демо-договор; банком выполнить демо-выдачу. Данные и ожидаемые статусы приведены
в [пошаговой инструкции](hackathon-start.md).

## Модульные и контрактные проверки

| Область | Команды | Рабочий каталог |
|---|---|---|
| Java, форматирование, интеграция БД | `mvn verify` | `backend/` |
| Python, контракты, scoring training | `uv sync --frozen`, `uv run --frozen pytest` | `fastapi/` |
| Python lint | `uv run --frozen ruff check app scripts tests scoring_training` | `fastapi/` |
| UI | `npm ci`, `npm run test -- --run`, `npm run build` | `frontend/` |

Для интеграционных Java-тестов нужен доступный Docker. Python integration-тесты
реальной модели включаются после явной подготовки пакета; стандартный pytest
использует тестовые fixtures. Количество тестов и результаты конкретного прогона
фиксируются в [отчётах задач](agents/log.md).

## Проверка реальных моделей и сквозных контрактов

После запуска Compose:

```sh
docker compose exec fastapi python -m scripts.verify_model --smoke
docker compose exec fastapi python -m scripts.prepare_scoring_model --smoke
```

Первая команда проверяет E5 manifest и embeddings, вторая — scoring package и
native CatBoost. Полные параметры подготовки описаны в
[MODEL_HANDOFF.md](../fastapi/MODEL_HANDOFF.md) и [SCORING_HF.md](../fastapi/SCORING_HF.md).

Из `fastapi/` доступны изолированные стенды:

```sh
uv run --frozen python -m scripts.java_acceptance --help
uv run --frozen python -m scripts.scoring_stack_acceptance --help
```

Они используют `compose.ml-test.yaml`, подготовленные модельные пакеты,
отдельные env-файлы и одноразовую БД. Точные параметры модели и образа проверяйте
через `--help`; штатные образы предварительно собираются из корня
`docker compose build backend fastapi`. Проверка HTTPS-cookie из корня:
`python scripts/check_cookie_https.py`. Скрипт создаёт и удаляет собственный стенд.

Повторная подача, обновление страницы, восстановление сессии, замена файла и
повторное чтение journey проверяются на сохранённых данных. Обычный `down`
сохраняет тома; отдельный Compose project изолирует проверку от рабочих данных.

## Инфраструктурные проверки db-init

Добавлены `compose.test.yaml`, CI `.github/workflows/tests.yaml`, JaCoCo и
проверка внешних ролей БД `CloudBootstrapTest`. Облачные шаблоны описаны в
[cloud-deployment.md](cloud-deployment.md).
