import { useEffect, useState } from 'react';
import { api, upload } from '../api';
import { normalizeAnswers } from '../form';
import { date, dictionaries, money, purposeNames, statusNames } from '../presentation';
import type { Answers, Application, Journey, Product } from '../types';
import { Banner, Button, Empty, Field, Icon, Select } from './UI';

type Requirement = { id: string; type_code: string; reason: string; status: string };
const documentNames: Record<string, string> = {
  TITLE: 'Документы о праве собственности',
  VALUATION: 'Оценка имущества',
  GUARANTEE_CONTRACT: 'Поручительство',
  INVOICE: 'Счёт или документы поставщика',
  BUSINESS_PLAN: 'Бизнес-план',
  PURPOSE_CONTRACT: 'Контракт по цели финансирования',
  DEBT_AGREEMENT: 'Договор действующего кредита',
  FINANCIAL_STATEMENTS: 'Финансовая отчётность',
  ACCOUNT_STATEMENT: 'Выписка по счёту',
};

export function ApplicationsPage({
  token,
  products,
  applicationId,
  onOpen,
  refresh,
  onStart,
}: {
  token: string;
  products: Product[];
  applicationId: string | null;
  onOpen: (id: string | null) => void;
  refresh: number;
  onStart: () => void;
}) {
  const [items, setItems] = useState<Application[]>([]),
    [journey, setJourney] = useState<Journey | null>(null);
  const [requirements, setRequirements] = useState<Requirement[]>([]),
    [answers, setAnswers] = useState<Answers>({});
  const [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [notice, setNotice] = useState('');
  const [confirmed, setConfirmed] = useState(false),
    [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    setNotice('');
    setJourney(null);
    setConfirmed(false);
    const load = async () => {
      if (applicationId) {
        const [result, docs] = await Promise.all([
          api<Journey>(`/applications/${applicationId}/journey`, token),
          api<Requirement[]>(`/applications/${applicationId}/requirements`, token),
        ]);
        if (active) {
          setJourney(result);
          setAnswers(result.application.answers);
          setRequirements(docs);
        }
      } else {
        const data = await api<{ content: Application[] }>('/applications?page=0&size=50', token);
        if (active) setItems(data.content);
      }
    };
    load()
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [token, applicationId, refresh, attempt]);
  const set = (path: string, value: string | number | boolean | null) => {
    const [section, key] = path.split('.');
    setAnswers((old) => ({ ...old, [section]: { ...old[section], [key]: value } }));
    setNotice('');
  };
  const value = (path: string) => {
    const [section, key] = path.split('.');
    return answers[section]?.[key] ?? '';
  };
  const field = (path: string, label: string, type: 'text' | 'number' | 'date' = 'text') => (
    <Field
      key={path}
      label={label}
      value={String(value(path))}
      type={type}
      onChange={(v) => set(path, type === 'number' ? (v === '' ? null : Number(v)) : v)}
    />
  );
  const select = (path: string, label: string, options: Record<string, string>) => (
    <Select
      key={path}
      label={label}
      value={String(value(path))}
      options={options}
      onChange={(v) => set(path, v)}
    />
  );
  const save = async () => {
    if (!journey || !applicationId) throw new Error('Заявка не загружена');
    const updated = await api<Journey['application']>(
      `/applications/${applicationId}`,
      token,
      { expectedVersion: journey.application.rowVersion, answers: normalizeAnswers(answers) },
      'PATCH',
    );
    setJourney({ ...journey, application: updated });
    setAnswers(updated.answers);
    return updated;
  };
  const perform = async (action: () => Promise<void>) => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await action();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось выполнить действие');
    } finally {
      setBusy(false);
    }
  };
  const saveDraft = () =>
    void perform(async () => {
      await save();
      setNotice('Изменения сохранены. Заявка пока не отправлена.');
    });
  const submit = () =>
    void perform(async () => {
      const draft = await save();
      await api(
        `/applications/${applicationId}/submit`,
        token,
        { expectedVersion: draft.rowVersion, confirmed: true },
        'POST',
        { 'Idempotency-Key': crypto.randomUUID() },
      );
      const updated = await api<Journey>(`/applications/${applicationId}/journey`, token);
      setJourney(updated);
      setNotice('Заявка отправлена. Статус рассмотрения появится в этом кабинете.');
    });
  const editable = journey && ['DRAFT', 'NEEDS_INFO'].includes(journey.application.status);
  const product = products.find((p) => p.versionId === journey?.application.productVersionId);
  return (
    <section className="account-page">
      {applicationId && (
        <button className="back-link" onClick={() => onOpen(null)} disabled={busy}>
          <Icon name="back" size={17} />
          Мои заявки
        </button>
      )}
      <div className="section-heading">
        <div>
          <span className="eyebrow">ЛИЧНЫЙ КАБИНЕТ</span>
          <h1>{applicationId ? 'Ваша заявка' : 'Мои заявки'}</h1>
          <p>
            {applicationId
              ? 'Проверьте сведения, дополните данные и следите за рассмотрением.'
              : 'Черновики, документы и статус рассмотрения — в одном месте.'}
          </p>
        </div>
        {!applicationId && (
          <Button view="accent" onClick={onStart} rightAddons={<Icon name="arrow" size={18} />}>
            Подобрать кредит
          </Button>
        )}
      </div>
      {error && (
        <Banner tone="error">
          {error}{' '}
          {loading === false && !journey && (
            <button className="text-action" onClick={() => setAttempt((n) => n + 1)}>
              Повторить
            </button>
          )}
        </Banner>
      )}
      {notice && <Banner tone="success">{notice}</Banner>}
      {loading ? (
        <div className="loading-panel" role="status">
          Загружаем заявки…
        </div>
      ) : !applicationId ? (
        items.length ? (
          <div className="saved-list">
            {items.map((item) => (
              <article key={item.id}>
                <span className="saved-icon">
                  <Icon name="file" />
                </span>
                <div>
                  <span className="saved-date">{date(item.created_at)}</span>
                  <h3>
                    {products.find((p) => p.versionId === item.product_version_id)?.name ??
                      'Заявка на финансирование'}
                  </h3>
                  <span className="pill">{statusNames[item.status] ?? 'На рассмотрении'}</span>
                </div>
                <Button
                  view="secondary"
                  size={40}
                  rightAddons={<Icon name="arrow" size={17} />}
                  onClick={() => onOpen(item.id)}
                >
                  Открыть
                </Button>
              </article>
            ))}
          </div>
        ) : (
          !error && (
            <Empty
              title="Пока нет заявок"
              action={
                <Button view="accent" onClick={onStart}>
                  Подобрать финансирование
                </Button>
              }
            >
              Выберите предложение после заполнения формы. Мы создадим черновик, который можно
              дополнить перед отправкой.
            </Empty>
          )
        )
      ) : (
        journey && (
          <div className="application-layout" key={applicationId}>
            <div className="application-main">
              <div className="application-overview">
                <span className="pill">
                  {statusNames[journey.application.status] ?? 'На рассмотрении'}
                </span>
                <h2>{product?.name ?? 'Финансирование бизнеса'}</h2>
                <p>
                  {money(String(journey.application.answers.request?.amount ?? ''))} ·{' '}
                  {String(journey.application.answers.request?.termMonths ?? '')} мес.
                </p>
              </div>
              {journey.decision && <Banner>{journey.decision.reason}</Banner>}
              <form
                className="application-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  submit();
                }}
              >
                <fieldset disabled={!editable || busy}>
                  <h2>Финансовые сведения</h2>
                  <p className="muted">
                    Ноль означает известное отсутствие обязательств. Если сведений нет, оставьте
                    поле пустым.
                  </p>
                  <div className="fields-grid form-spaced">
                    {field('financial.monthlyDebtPayment', 'Текущие платежи по долгам, ₽')}
                    <Field
                      label="Доля просроченных платежей, %"
                      value={
                        value('financial.overdue') === ''
                          ? ''
                          : String(Number(value('financial.overdue')) * 100)
                      }
                      onChange={(v) => {
                        const numeric = Number(v.replace(',', '.'));
                        if (
                          v.trim() !== '' &&
                          (!Number.isFinite(numeric) || numeric < 0 || numeric > 100)
                        ) {
                          setError('Долю просрочек нужно указать числом от 0 до 100.');
                          return;
                        }
                        set('financial.overdue', v.trim() === '' ? null : numeric / 100);
                      }}
                      hint="От 0 до 100. Если просрочек не было — 0."
                    />
                    {field('security.collateralValue', 'Стоимость предлагаемого залога, ₽')}
                    {field('project.ownContributionPct', 'Собственное участие, %')}
                  </div>
                  <details className="application-answers">
                    <summary>Сведения из вашей анкеты</summary>
                    <div className="fields-grid form-spaced">
                      {field('request.amount', 'Сумма финансирования, ₽')}
                      {field('request.termMonths', 'Срок, месяцев', 'number')}
                      {select('request.purpose', 'Цель финансирования', purposeNames)}
                      {select('business.sector', 'Сфера деятельности', {
                        '': 'Уточню позже',
                        ...dictionaries.sectors,
                      })}
                      {field('business.actualStartedOn', 'Начало деятельности', 'date')}
                      {select('business.taxRegime', 'Система налогообложения', {
                        UNKNOWN: 'Уточню позже',
                        OSNO: 'ОСНО',
                        USN: 'УСН',
                        AUSN: 'АУСН',
                        ...(value('registration.borrowerKind') === 'IP'
                          ? { PSN: 'Патент', NPD: 'НПД' }
                          : {}),
                      })}
                      <Select
                        label="Компания в реестре МСП"
                        value={String(value('business.mspRegistry'))}
                        options={{ '': 'Уточню позже', true: 'Да', false: 'Нет' }}
                        onChange={(v) =>
                          set('business.mspRegistry', v === '' ? null : v === 'true')
                        }
                      />
                      {field('financial.revenue', 'Выручка за период, ₽')}
                      {field('financial.periodFrom', 'Начало периода', 'date')}
                      {field('financial.periodTo', 'Конец периода', 'date')}
                      {select(
                        'security.collateralReady',
                        'Имущественный залог',
                        dictionaries.readiness,
                      )}
                      {select('security.guarantorReady', 'Поручительство', dictionaries.readiness)}
                    </div>
                  </details>
                  {editable && (
                    <>
                      <label className="confirmation">
                        <input
                          type="checkbox"
                          checked={confirmed}
                          onChange={(e) => setConfirmed(e.target.checked)}
                        />
                        Подтверждаю сведения анкеты и хочу отправить заявку на рассмотрение.
                      </label>
                      <div className="application-actions">
                        <Button
                          view="secondary"
                          size={48}
                          type="button"
                          onClick={saveDraft}
                          loading={busy}
                        >
                          Сохранить черновик
                        </Button>
                        <Button view="accent" size={48} type="submit" disabled={!confirmed || busy}>
                          Отправить заявку
                        </Button>
                      </div>
                    </>
                  )}
                </fieldset>
              </form>
              <section className="documents-panel">
                <h2>Документы</h2>
                {requirements.length ? (
                  <div className="document-list">
                    {requirements.map((doc) => (
                      <div key={doc.id}>
                        <span className="document-icon">
                          <Icon name="file" />
                        </span>
                        <div>
                          <strong>
                            {documentNames[doc.type_code] ?? 'Документ по условиям продукта'}
                          </strong>
                          <p>{doc.reason}</p>
                          <small>
                            {doc.status === 'VERIFIED'
                              ? 'Проверен'
                              : doc.status === 'WAIVED'
                                ? 'Не требуется'
                                : doc.status === 'REQUIRED'
                                  ? 'Нужен документ'
                                  : doc.status === 'NEEDS_CORRECTION'
                                    ? 'Нужно исправить'
                                    : 'Получен, ожидает проверки'}
                          </small>
                        </div>
                        {editable && (
                          <label className={`upload-label ${busy ? 'disabled' : ''}`}>
                            Добавить файл
                            <input
                              aria-label={`Загрузить: ${documentNames[doc.type_code] ?? doc.type_code}`}
                              type="file"
                              accept="application/pdf,image/png,image/jpeg"
                              disabled={busy}
                              onChange={(e) => {
                                const file = e.target.files?.[0];
                                e.target.value = '';
                                if (!file) return;
                                void perform(async () => {
                                  const body = new FormData();
                                  body.set('typeCode', doc.type_code);
                                  body.set('file', file);
                                  await upload(
                                    `/applications/${applicationId}/documents`,
                                    token,
                                    body,
                                  );
                                  const updated = await api<Journey>(
                                    `/applications/${applicationId}/journey`,
                                    token,
                                  );
                                  setJourney(updated);
                                  setNotice('Документ загружен и ожидает проверки.');
                                });
                              }}
                            />
                          </label>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="muted">
                    По текущим условиям дополнительные документы не запрошены. При рассмотрении
                    список может измениться.
                  </p>
                )}
                <p className="fine-print">
                  PDF, PNG или JPEG, до 10 МБ. Загрузка документа не означает, что он прошёл
                  проверку.
                </p>
              </section>
            </div>
            <aside className="application-aside">
              <div className="summary-card">
                <span className="summary-label">СТАТУС РАССМОТРЕНИЯ</span>
                <h3>{statusNames[journey.application.status] ?? 'На рассмотрении'}</h3>
                <p>Возвращайтесь в кабинет, чтобы проверить результат.</p>
                <button
                  className="text-action"
                  disabled={busy}
                  onClick={() => setAttempt((n) => n + 1)}
                >
                  Обновить статус
                </button>
              </div>
              {!!journey.history.length && (
                <ol className="status-history">
                  {journey.history.map((event, i) => (
                    <li key={i}>
                      <span />
                      <div>
                        <strong>{statusNames[event.toStatus] ?? 'Статус обновлён'}</strong>
                        <small>{date(event.createdAt)}</small>
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </aside>
          </div>
        )
      )}
    </section>
  );
}
