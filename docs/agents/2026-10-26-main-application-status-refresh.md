# main: отображение подтверждения и актуальных статусов заявки

## Запрос и диагностика

Пользователь сообщил, что на backend можно дойти до подтверждения, но frontend
не показывает его; попросил найти и исправить ошибку в окончательной ветке main.
Исходный HEAD main: b697af1, рабочее дерево чистое. Выполнены независимые read-only
аудиты backend и frontend. Journey API и статусы совпадают: APPROVED → OFFER_ACCEPTED
→ SIGNED → DISBURSED, все соответствующие UI-блоки уже есть.

Причина: ApplicationsPage загружает journey только при открытии, ручном refresh
или своей операции. Внешний bank /process не меняет React dependencies и экран
сохраняет SUBMITTED. Аналогично BankPage не узнаёт о принятии/подписании владельцем.

## Исправление

Добавляется bounded polling раз в 5 секунд видимой вкладки, обновление при focus/
visibility, без пересекающихся запросов и с cleanup при закрытии экрана. Обновление
проверяет application id, rowVersion и поколение пользовательской операции, чтобы
поздний GET не откатил результат accept/sign. Равная версия допускается: reviews
документов/checks могут измениться без повышения версии application.

Редактируемые DRAFT/NEEDS_INFO не перезагружаются фоново, данные и autosave
сохраняются. Текущие checkbox-подтверждения сохраняются при неизменном предложении
и сбрасываются при смене статуса/предложения. Клиентские мутации по-прежнему требуют
явного согласия и штатного cookie/CSRF API. Backend и ML-контракты не меняются.

## Изменённые файлы

- `frontend/src/liveRefresh.ts`: контроллер обновления видимой вкладки с focus,
  visibility, timeout после завершения запроса, без повторного initial load.
- `Applications.tsx`: фоновые GET journey/requirements/documents для ожидающих
  статусов и обновление списка заявок, без полной перезагрузки редактора. Сохраняются
  checkbox согласия с тем же предложением; при смене статуса/предложения сбрасываются.
- `Bank.tsx`: обновление очереди, выбранного journey и документов без сброса
  заполненного банковского form; подтверждение выдачи сбрасывается при смене статуса.
- `journeyRefresh.ts`: ожидающие статусы и проверка id/версии снимка. Поздний ответ
  после начала локального действия также отбрасывается через поколение операции.
- Unit-файлы `live-refresh.test.mjs`, `journey-refresh.test.mjs` добавлены в `npm test`.
  Dependency versions и package-lock не менялись.

## Выполненные проверки

1. `npm ci --prefix frontend --no-audit --no-fund` прошёл.
2. `npm --prefix frontend test` на bundled Node **24.22.1**: **44 passed**, без
   failures/skips. Существующие 34 + 7 проверок polling/visibility/cleanup/retry +
   3 проверки статусов/id/версий. Полные повторные ML/Maven suite не запускались:
   backend и модели не менялись.
3. `npm --prefix frontend run build`: TypeScript + Vite production **passed**,
   451 modules transformed. Prettier изменённых файлов и `git diff --check` прошли.
4. Настоящий headless **Microsoft Edge** через Playwright, React.StrictMode,
   standalone реальные ApplicationsPage и BankPage с ответами API по текущему
   backend-контракту: **5 сценариев passed**, **0 page errors**.
   Это UI-интеграционные проверки с mock API, без запуска ML/PostgreSQL.
   [JSON-отчёт](artifacts/2026-10-26-main-status-refresh/browser-regression.json).
   Проверены:
   - Точный исходный Applications.tsx из HEAD b697af1: после внешнего APPROVED
     и 6 секунд экран остаётся SUBMITTED; новых GET нет, кнопки принятия нет.
   - Исправленный экран: предложение появляется после 5-секундного polling;
     отмеченное согласие не сбрасывается следующим GET; принятие и подписание
     отображаются сразу; внешняя DISBURSED автоматически появляется.
   - Переход SUBMITTED → NEEDS_INFO открывает редактирование с актуальной версией;
     autosave отправляет правильный expectedVersion, дальнейший polling не стирает
     введённое значение.
   - Задержанный GET старого APPROVED после успешного принятия не откатывает
     OFFER_ACCEPTED и экран подписания.
   - Банк видит внешнее подписание клиентом автоматически без ручного refresh.
5. Сделаны screenshot артефакты; визуально проверено готовое предложение и его checkbox/button:
   [до исправления](artifacts/2026-10-26-main-status-refresh/before-stale-submitted.png),
   [готовое предложение](artifacts/2026-10-26-main-status-refresh/after-live-approval.png),
   [подписание в кабинете банка](artifacts/2026-10-26-main-status-refresh/bank-sees-signed.png).
   Временные baseline-компонент и test entry удалены после прогона. Playwright
   harness сохранён в игнорируемом `work/test-main-status-refresh.cjs`.

## Границы и Git

Изменения находятся на main поверх b697af1. Новые backend endpoints, поля,
DB migrations, SSE/WebSocket или автоматические банковские решения не вводились:
polling запрашивает текущие данные, а принятие/подписание по-прежнему требуют
действия пользователя. У hidden вкладки опрос остановлен; при возврате обновление
немедленное. Открытые editable черновики намеренно не заменяются server snapshot;
для них остаётся безопасное ручное обновление с сохранением формы. При сетевом
сбое показано предупреждение и продолжаются ограниченные повторные GET.

Основной Docker stack на момент начала остановлен; основной frontend не
перезапускался. `docker build -t alpha-future-frontend:local ./frontend` прошёл:
Node 22-alpine, TypeScript/Vite и nginx runtime image; production bundle совпадает
с host build (index-Cf89lTCD.js). Локальный Vite и headless browser после проверки
остановлены, временных test entry в source нет. Внешнее развёртывание, commit и
push не выполнялись. Исторические отчёты сохранены.
