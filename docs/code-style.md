# Стиль кода и рабочие команды

[Навигация](README.md) · [Проверки](validation.md)

Java-код форматируется Spotless по настройкам Maven. Используйте Java 21;
команды выполняются из `backend/`:

```sh
mvn spotless:apply
mvn verify
```

Для локального запуска установите Maven 3.9+ и Java 21. Миграции Flyway добавляются новыми версиями;
применённые V-миграции сохраняют неизменный checksum. API принимает явные DTO,
денежные значения обрабатываются Decimal/BigDecimal, время процесса — в UTC.

Frontend использует TypeScript и React. Команды из `frontend/`:

```sh
npm ci
npm run test -- --run
npm run build
```

FastAPI использует Python 3.11, lock-файл uv и Ruff. Из `fastapi/`:

```sh
uv sync --frozen
uv run --frozen ruff check app scripts tests scoring_training
uv run --frozen pytest
```

Новые изменения описываются отдельным отчётом в `docs/agents/` со ссылкой из
общего индекса. В отчёте указываются реально выполненные проверки, затронутые
контракты и Git-состояние; секреты и персональные данные не записываются.
