# Обновление acceptance fixture одобрения для scoring v2

## Запрос

Пользователь спросил, как исправить расхождение: старый интеграционный тест
ожидает APPROVED, но закреплённый native пакет v2 возвращает DECLINED.
Рабочая ветка — `scoring_model`; предыдущие незакоммиченные изменения HF-источника
сохранены. Изменение касается тестового сценария, без переобучения и смены policy.

## Диагностика

Старая fixture: P01, 300000 RUB, 12 месяцев, ставка 28%, действующий бизнес.
Local и HF v2 совпадают: p=0.2525274156209339. В Java прямое одобрение требует
finalRiskScore<=0.15, подходящего PTI и суммы. При p между 0.15 и 0.35 допускается
попытка контрпредложения. Для этой fixture сумма/срок/ставка альтернативы не
отличаются от исходных, поэтому Java возвращает NO_ACCEPTABLE_COUNTEROFFER.
Это не transport error и не порог бинарной классификации CatBoost.

Проверка отдельных изменений сектора, формы, возраста бизнеса и обеспечения
при прежних сумме/сроке/ставке не снижает p данного пакета. Обходить проверку
подменой ожидаемого APPROVED на DECLINED означало бы потерять ветку одобрения.

## Изменение

В `fastapi/scripts/scoring_stack_acceptance.py` для APPROVED выбран существующий
синтетический продукт P07: цель EQUIPMENT, 500000 RUB, 60 месяцев, ставка каталога
22%, collateralReady=YES, collateralValue=1000000 RUB, ownContributionPct=20.
Эти значения укладываются в границы P07; synthetic STABLE имеет достаточную
историю и выручку. Native v2 smoke для соответствующих девяти признаков дал
p=0.006003678384059744, score=99. Остальные три fixture остаются на P01.
В JSON-отчёт добавлен productCode для воспроизводимости.

Модель, её operating threshold, калибратор и Java risk/PTI rules не изменяются.
Подбор synthetic branch fixtures не является независимой оценкой ML-качества
и не используется для подбора порога или обучения. Scope --source-smoke сохранён.

## Проверки

`python -X utf8 -m scripts.scoring_stack_acceptance --output reports/scoring-v2-four-outcomes.json`
прошёл на отдельном disposable Docker stack с настоящими E5 и HF native v2.
Проверены nginx/frontend, Java, FastAPI и PostgreSQL. Фактические исходы:
APPROVED, COUNTEROFFERED, DECLINED, REQUEST_INFO. Для APPROVED и COUNTEROFFERED
выполнены подтверждение условий, подписание договора и выдача до DISBURSED.
В БД четыре оценки, три связанных решения, только modelVersion sba-scoring-v2.
Дополнительно выполнена исходная HTTP scoring-нагрузка рядом с E5; ranking неизменен.
Временные containers/volumes удалены, пользовательский основной stack не менялся.
[Полный JSON-результат](artifacts/2026-10-26-scoring-v2-journey/four-outcomes.json).

Ruff check/format и git diff --check прошли. Отдельный Maven/Python full suite
повторно не запускался: меняется только acceptance script и документация.
В `SCORING_HF.md` устранено устаревшее ограничение о неработающей approval fixture;
предыдущий task report сохранён как история до исправления. Изменения находятся
на scoring_model вместе с предыдущей миграцией HF. Коммиты и push не выполнялись.
