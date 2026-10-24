import type { Candidate, Product, SavedSelection, Selection } from '../types';
import { date, money, purposeNames } from '../presentation';
import { ProductCard } from './Catalog';
import { Banner, Button, Empty, Icon } from './UI';

export function SelectionResults({
  selection,
  onDetails,
  onChoose,
  onRetry,
  onEdit,
  busy,
}: {
  selection: Selection;
  onDetails: (p: Product) => void;
  onChoose: (c: Candidate) => void;
  onRetry: () => void;
  onEdit: () => void;
  busy: boolean;
}) {
  return (
    <section className="results-page">
      <div className="section-heading">
        <div>
          <span className="eyebrow">ВАШ ПОДБОР</span>
          <h1>
            {selection.results.length
              ? 'Предложения под\nвашу задачу.'
              : 'Изменим условия\nи попробуем снова.'}
          </h1>
          <p>Проверка от {date(selection.asOf)}. Перед оформлением можно изучить все условия.</p>
        </div>
        <Button view="secondary" size={48} onClick={onEdit} disabled={busy}>
          Изменить ответы
        </Button>
      </div>
      {!selection.current ? (
        <Banner>
          Вы изменили данные компании. Обновите подбор, чтобы увидеть актуальные условия.
        </Banner>
      ) : selection.results.length > 0 && selection.rankingStatus !== 'READY' ? (
        <Banner>
          <strong>Условия продуктов проверены</strong>
          <p>
            Персональный подбор сейчас недоступен. Ниже — продукты, которые прошли предварительную
            проверку. Вы можете изучить их или повторить подбор позднее.
          </p>
          <button className="text-action" disabled={busy} onClick={onRetry}>
            {busy ? 'Проверяем…' : 'Повторить подбор'}
          </button>
        </Banner>
      ) : selection.results.length > 0 ? (
        <div className="result-summary">
          <span>
            <Icon name="check" size={18} />
            {selection.results.length} подходящих вариантов
          </span>
          <p>Выделили предложения по вашей задаче. Это не гарантирует одобрение.</p>
        </div>
      ) : null}
      {selection.results.length ? (
        <div className="product-grid">
          {selection.results.map((c) => (
            <ProductCard
              product={c.product}
              key={c.productVersion}
              onDetails={onDetails}
              onStart={() => onChoose(c)}
              recommended={c.isRecommended}
              disabled={busy || !selection.current}
              actionLabel="Начать оформление"
            >
              {c.pendingConditions.length > 0 && (
                <div className="pending-conditions">
                  <strong>
                    <Icon name="shield" size={16} />
                    Что нужно уточнить
                  </strong>
                  <ul>
                    {c.pendingConditions.slice(0, 2).map((condition, i) => (
                      <li key={`${condition.code}-${i}`}>{condition.message}</li>
                    ))}
                  </ul>
                  {c.pendingConditions.length > 2 && (
                    <details>
                      <summary>
                        Ещё {c.pendingConditions.length - 2}{' '}
                        {c.pendingConditions.length - 2 === 1 ? 'условие' : 'условия'}
                      </summary>
                      <ul>
                        {c.pendingConditions.slice(2).map((condition, i) => (
                          <li key={i}>{condition.message}</li>
                        ))}
                      </ul>
                    </details>
                  )}
                </div>
              )}
            </ProductCard>
          ))}
        </div>
      ) : (
        <Empty
          title="Сейчас подходящих продуктов нет"
          action={
            <Button view="accent" onClick={onEdit}>
              Изменить параметры
            </Button>
          }
        >
          Возможно, стоит скорректировать сумму, срок или цель. Причины проверки можно посмотреть
          ниже.
        </Empty>
      )}
      {selection.excluded.length > 0 && (
        <details className="excluded-products">
          <summary>Почему другие продукты не подошли ({selection.excluded.length})</summary>
          <div>
            {selection.excluded.map((item) => (
              <article key={item.productCode}>
                <h3>Продукт {item.productCode.replace(/^P/, '№ ')}</h3>
                <ul>
                  {item.reasons
                    .filter((r) => r.result === 'FAIL')
                    .map((reason, i) => (
                      <li key={i}>{reason.message}</li>
                    ))}
                </ul>
              </article>
            ))}
          </div>
        </details>
      )}
      <p className="catalog-disclosure">
        Проверка учитывает сведения из вашей формы и условия каталога. Неизвестные сведения
        потребуется уточнить. Окончательное решение принимается после рассмотрения заявки.
      </p>
    </section>
  );
}
export function SavedSelections({
  items,
  onOpen,
  onStart,
  busy,
}: {
  items: SavedSelection[];
  onOpen: (item: SavedSelection) => void;
  onStart: () => void;
  busy: boolean;
}) {
  return (
    <section className="account-page">
      <div className="section-heading">
        <div>
          <span className="eyebrow">ЛИЧНЫЙ КАБИНЕТ</span>
          <h1>Мои подборы</h1>
          <p>Сохранённые ответы и предложения — можно вернуться к ним в любое время.</p>
        </div>
        <Button view="accent" onClick={onStart}>
          Новый подбор
          <Icon name="arrow" size={18} />
        </Button>
      </div>
      {items.length ? (
        <div className="saved-list">
          {items.map((item) => (
            <article key={item.id}>
              <span className="saved-icon">
                <Icon name="brief" />
              </span>
              <div>
                <span className="saved-date">{date(item.created_at)}</span>
                <h3>
                  {purposeNames[String(item.answers.request?.purpose)] ?? 'Финансирование бизнеса'}
                </h3>
                <p>{item.company_name.replace(/^DEMO:\s*/, '')}</p>
              </div>
              <strong>
                {money(String(item.answers.request?.amount ?? ''))}
                <small>{String(item.answers.request?.termMonths ?? '')} мес.</small>
              </strong>
              <Button view="secondary" size={40} disabled={busy} onClick={() => onOpen(item)}>
                {item.run_id ? 'Посмотреть' : 'Продолжить'}
                <Icon name="arrow" size={17} />
              </Button>
            </article>
          ))}
        </div>
      ) : (
        <Empty
          title="Здесь будут ваши подборы"
          action={
            <Button view="accent" onClick={onStart}>
              Подобрать финансирование
            </Button>
          }
        >
          Расскажите о бизнесе и цели. Мы сохраним ответы и доступные предложения в вашем кабинете.
        </Empty>
      )}
    </section>
  );
}
