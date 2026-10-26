# Исходные требования и материалы проектирования

[Назад к документации](../README.md)

Здесь сохранены исходные тексты требований и аналитические материалы этапов
проектирования. Их содержание отражает дату подготовки; формулировки предложений,
прежние количества полей и проектные схемы читаются в этом историческом контексте.
Действующее поведение описывают [API](../backend-api.md),
[контракт полей](../backend-fields-v3.md), [политика](../data-policy.md) и
[скоринг](../credit-scoring.md). Для запуска используйте [инструкцию](../hackathon-start.md).

| Материал | Содержание |
|---|---|
| [credit-journey.md](credit-journey.md) | Исходное проектирование кредитного пути |
| [preliminary-form.md](preliminary-form.md) | Первоначальная предварительная форма |
| [preliminary-form-2.0.md](preliminary-form-2.0.md) | Требования к новой предварительной форме |
| [full-application.md](full-application.md) | Исходная спецификация полного досье |
| [data-policy-3.0.md](data-policy-3.0.md) | Исходная постановка финансовой политики |
| [query-passage-mvp-source.md](query-passage-mvp-source.md) | Исходный контракт текстового подбора |
| [dataset-fields-review.md](dataset-fields-review.md) | Анализ признаков датасета |

Планы [реализации скоринга](../credit-scoring-implementation-plan.md) и
[экспериментов 90/60](../scoring-retraining-recall90-precision60-plan.md)
сохраняются как история решений. Результаты экспериментов и актуальная модель:
[индекс ML](../../fastapi/experiments/README.md).
