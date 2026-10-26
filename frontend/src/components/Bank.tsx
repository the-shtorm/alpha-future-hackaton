import { useEffect, useRef, useState } from 'react';
import { api, ApiError } from '../api';
import { date, money, statusNames } from '../presentation';
import type { Application, Journey, Product } from '../types';
import { Banner, Button, Field, Select } from './UI';
import { documentNames } from './Applications';

type Document = {
  id: string;
  filename: string;
  typeCode: string;
  reviewResult: string | null;
  current: boolean;
};
type Macro = { keyRatePct: string; expiresAt: string; sourceCode: string };
export function BankPage({ products }: { products: Product[] }) {
  const [page, setPage] = useState(0),
    [total, setTotal] = useState(0);
  const [items, setItems] = useState<Application[]>([]),
    [id, setId] = useState('');
  const [journey, setJourney] = useState<Journey | null>(null),
    [documents, setDocuments] = useState<Document[]>([]);
  const [macro, setMacro] = useState<Macro | null>(null);
  const [rate, setRate] = useState(''),
    [source, setSource] = useState(''),
    [expiry, setExpiry] = useState('');
  const [reason, setReason] = useState(''),
    [kind, setKind] = useState('REQUEST_INFO');
  const [missing, setMissing] = useState('financial.monthlyDebtPayment');
  const [confirmed, setConfirmed] = useState(false);
  const [tick, setTick] = useState(0),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const acting = useRef(false);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    setJourney(null);
    setDocuments([]);
    setConfirmed(false);
    setReason('');
    Promise.all([
      api<{ content: Application[]; totalElements: number }>(
        `/bank/applications?page=${page}&size=20`,
      ),
      api<Macro>('/bank/macroeconomic-contexts/current').catch((e) => {
        if (e instanceof ApiError && e.code === 'MACRO_CONTEXT_REQUIRED') return null;
        throw e;
      }),
      id ? api<Journey>(`/applications/${id}/journey`) : Promise.resolve(null),
      id ? api<Document[]>(`/applications/${id}/documents`) : Promise.resolve([]),
    ])
      .then(([queue, context, current, docs]) => {
        if (!active) return;
        setItems(queue.content);
        setTotal(queue.totalElements);
        setMacro(context);
        setJourney(current);
        setDocuments(docs.filter((doc) => doc.current));
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [id, page, tick]);
  const perform = async (action: () => Promise<unknown>) => {
    if (acting.current) return;
    acting.current = true;
    setBusy(true);
    setError('');
    try {
      await action();
      setTick((n) => n + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Операция не выполнена');
    } finally {
      acting.current = false;
      setBusy(false);
    }
  };
  const blocked = busy || loading;
  const status = journey?.application.status;
  const reviewable = status && ['DRAFT', 'SUBMITTED', 'NEEDS_INFO'].includes(status);
  const decidable = status && ['SUBMITTED', 'UNDER_REVIEW'].includes(status);
  return (
    <section className="account-page">
      <div className="section-heading">
        <div>
          <span className="eyebrow">БАНК</span>
          <h1>Рассмотрение заявок</h1>
        </div>
        <Button disabled={blocked} view="secondary" onClick={() => setTick((n) => n + 1)}>
          Обновить
        </Button>
      </div>
      {error && <Banner tone="error">{error}</Banner>}
      <details className="application-overview">
        <summary>Макроэкономический контекст</summary>
        {macro ? (
          <p>
            Ставка {macro.keyRatePct}% · до {date(macro.expiresAt)} · {macro.sourceCode}
          </p>
        ) : (
          <Banner>
            Нет действующего контекста. Укажите проверенную ставку и источник перед рассмотрением.
          </Banner>
        )}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void perform(async () => {
              const expires = new Date(expiry);
              if (!rate || !source.trim() || !Number.isFinite(expires.getTime()))
                throw new Error('Заполните ставку, источник и срок действия.');
              await api('/bank/macroeconomic-contexts', {
                keyRatePct: rate,
                sourceCode: source.trim(),
                validFrom: new Date(Date.now() - 1000).toISOString(),
                expiresAt: expires.toISOString(),
              });
              setRate('');
              setSource('');
              setExpiry('');
            });
          }}
        >
          <fieldset disabled={blocked}>
            <div className="fields-grid">
              <Field label="Ключевая ставка, %" value={rate} onChange={setRate} />
              <Field label="Источник ставки" value={source} onChange={setSource} />
              <Field
                label="Действует до"
                type="datetime-local"
                value={expiry}
                onChange={setExpiry}
              />
            </div>
            <Button type="submit" disabled={blocked || !rate || !source || !expiry}>
              Сохранить контекст
            </Button>
          </fieldset>
        </form>
      </details>
      <div className="application-layout">
        <div className="application-main">
          {id && (
            <Button view="secondary" disabled={blocked} onClick={() => setId('')}>
              К очереди
            </Button>
          )}
          {loading ? (
            <p role="status">Загружаем заявки…</p>
          ) : !id ? (
            <>
              {!items.length && <p>Заявок пока нет.</p>}
              <div className="saved-list">
                {items.map((item) => (
                  <article key={item.id}>
                    <div>
                      <h3>
                        {products.find((p) => p.versionId === item.product_version_id)?.name ??
                          'Заявка'}
                      </h3>
                      <p>
                        {date(item.created_at)} · {statusNames[item.status] ?? item.status}
                      </p>
                    </div>
                    <Button view="secondary" disabled={blocked} onClick={() => setId(item.id)}>
                      Рассмотреть
                    </Button>
                  </article>
                ))}
              </div>
              <div className="fields-grid">
                <Button disabled={blocked || page === 0} onClick={() => setPage((n) => n - 1)}>
                  Назад
                </Button>
                <p>
                  Страница {page + 1} · всего {total}
                </p>
                <Button
                  disabled={blocked || (page + 1) * 20 >= total}
                  onClick={() => setPage((n) => n + 1)}
                >
                  Далее
                </Button>
              </div>
            </>
          ) : (
            journey && (
              <>
                <h2>{statusNames[journey.application.status] ?? journey.application.status}</h2>
                <p>
                  Запрошено: {money(String(journey.application.answers.request?.amount ?? ''))} ·{' '}
                  {String(journey.application.answers.request?.termMonths ?? '')} мес.
                </p>
                <p>
                  Выручка за период:{' '}
                  {money(String(journey.application.answers.financial?.revenue ?? ''))}; текущие
                  ежемесячные платежи:{' '}
                  {money(String(journey.application.answers.financial?.monthlyDebtPayment ?? ''))}
                </p>
                {journey.decision && <Banner>{journey.decision.reason}</Banner>}
                {journey.offer && (
                  <section className="application-overview">
                    <h2>Согласованные условия</h2>
                    <p>
                      {money(journey.offer.terms.amount)} · {journey.offer.terms.termMonths} мес. ·{' '}
                      {journey.offer.terms.annualRatePct}% годовых
                    </p>
                  </section>
                )}
                {journey.counteroffer && !journey.offer && (
                  <section className="application-overview">
                    <h2>Условия контроффера</h2>
                    <p>
                      {money(journey.counteroffer.alternative_terms.amount)} ·{' '}
                      {journey.counteroffer.alternative_terms.termMonths} мес. ·{' '}
                      {journey.counteroffer.alternative_terms.annualRatePct}% годовых
                    </p>
                  </section>
                )}
                <h2>Документы</h2>
                {!documents.length && <p>Документы не загружены.</p>}
                <Field
                  label="Комментарий к проверке или решению"
                  value={reason}
                  onChange={setReason}
                />
                <div className="saved-list">
                  {documents.map((doc) => (
                    <article key={doc.id}>
                      <div>
                        <a
                          href={`/api/applications/${id}/documents/${doc.id}`}
                          target="_blank"
                          rel="noreferrer"
                        >
                          {doc.filename}
                        </a>
                        <p>
                          {documentNames[doc.typeCode] ?? 'Документ'} ·{' '}
                          {['CREDIT_CONTRACT', 'CONTRACT'].includes(doc.typeCode)
                            ? 'Сформирован в системе'
                            : doc.reviewResult === 'PASS'
                              ? 'Проверен'
                              : doc.reviewResult === 'FAIL'
                                ? 'Отклонён'
                                : 'Требует проверки'}
                        </p>
                      </div>
                      {reviewable && (
                        <div className="fields-grid">
                          {['PASS', 'FAIL'].map((result) => (
                            <Button
                              key={result}
                              size={40}
                              disabled={blocked || !reason.trim()}
                              onClick={() =>
                                void perform(() =>
                                  api(`/bank/applications/${id}/documents/${doc.id}/review`, {
                                    result,
                                    reason: reason.trim(),
                                  }),
                                )
                              }
                            >
                              {result === 'PASS' ? 'Подтвердить документ' : 'Отклонить документ'}
                            </Button>
                          ))}
                        </div>
                      )}
                    </article>
                  ))}
                </div>
                {decidable && (
                  <>
                    <Button
                      view="accent"
                      disabled={blocked}
                      onClick={() =>
                        void perform(() => api(`/bank/applications/${id}/process`, {}))
                      }
                    >
                      Запустить проверки и скоринг
                    </Button>
                    <details className="application-overview">
                      <summary>Решение сотрудника</summary>
                      <p>
                        Положительное решение возможно только после прохождения серверных проверок.
                      </p>
                      <Select
                        label="Решение"
                        value={kind}
                        onChange={setKind}
                        options={{
                          REQUEST_INFO: 'Запросить сведения',
                          APPROVED: 'Подтвердить одобрение',
                          COUNTEROFFERED: 'Подтвердить контроффер',
                          DECLINED: 'Отказать',
                        }}
                      />
                      {kind === 'REQUEST_INFO' && (
                        <Select
                          label="Недостающее сведение"
                          value={missing}
                          onChange={setMissing}
                          options={{
                            'financial.monthlyDebtPayment': 'Платежи по действующим долгам',
                            'financial.overdue': 'Доля просрочки',
                            'financial.revenue': 'Выручка',
                            documents: 'Документы',
                          }}
                        />
                      )}
                      <Button
                        disabled={blocked || !reason.trim()}
                        onClick={() =>
                          void perform(() =>
                            api(`/bank/applications/${id}/decisions`, {
                              kind,
                              reason: reason.trim(),
                              missingFields: kind === 'REQUEST_INFO' ? [missing] : [],
                            }),
                          )
                        }
                      >
                        Сохранить решение
                      </Button>
                    </details>
                  </>
                )}
                {status === 'SIGNED' && (
                  <section className="application-overview">
                    <h2>Демонстрационная выдача</h2>
                    <label className="confirmation">
                      <input
                        type="checkbox"
                        checked={confirmed}
                        disabled={blocked}
                        onChange={(e) => setConfirmed(e.target.checked)}
                      />
                      Подтверждаю учебную выдачу по подписанным условиям
                    </label>
                    <Button
                      disabled={blocked || !confirmed}
                      onClick={() =>
                        void perform(() =>
                          api(`/bank/applications/${id}/disburse`, { confirmed: true }),
                        )
                      }
                    >
                      Выполнить демо-выдачу
                    </Button>
                  </section>
                )}
                {journey.disbursements?.map((payment) => (
                  <Banner tone="success" key={payment.id}>
                    Выдача выполнена: {money(payment.amount)} · {date(payment.executedAt)}
                  </Banner>
                ))}
              </>
            )
          )}
        </div>
      </div>
    </section>
  );
}
