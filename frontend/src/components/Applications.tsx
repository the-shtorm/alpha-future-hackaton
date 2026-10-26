import { useEffect, useRef, useState } from 'react';
import { api, upload, ApiError } from '../api';
import { sameAnswers } from '../form';
import { DraftWriter } from '../drafts';
import { date, dictionaries, money, purposeNames, statusNames } from '../presentation';
import type { Answers, Application, Journey, Product } from '../types';
import { Banner, Button, Empty, Field, Icon, Select } from './UI';

type UploadedDocument = {
  id: string;
  typeCode: string;
  filename: string;
  versionNo: number;
  current: boolean;
  reviewResult: string | null;
};
type Requirement = { id: string; type_code: string; reason: string; status: string };
export const documentNames: Record<string, string> = {
  CREDIT_CONTRACT: 'Демонстрационный договор',
  CONTRACT: 'Демонстрационный договор',
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
  products,
  applicationId,
  onOpen,
  refresh,
  onStart,
  registerSave,
  externalBusy,
}: {
  products: Product[];
  applicationId: string | null;
  onOpen: (id: string | null) => void;
  refresh: number;
  onStart: () => void;
  externalBusy: boolean;
  registerSave: (save: (() => Promise<void>) | null) => void;
}) {
  const [items, setItems] = useState<Application[]>([]),
    [journey, setJourney] = useState<Journey | null>(null);
  const [requirements, setRequirements] = useState<Requirement[]>([]),
    [answers, setAnswers] = useState<Answers>({});
  const [documents, setDocuments] = useState<UploadedDocument[]>([]);
  const [replacements, setReplacements] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [notice, setNotice] = useState('');
  const writer = useRef<DraftWriter<Journey['application']> | null>(null);
  const acting = useRef(false);
  const [saving, setSaving] = useState(0);
  const [draftError, setDraftError] = useState('');
  const pendingSubmission = useRef<{ id: string; version: number; key: string } | null>(null);
  const [submissionUncertain, setSubmissionUncertain] = useState(false);
  const [counterConfirmed, setCounterConfirmed] = useState(false);
  const [offerConfirmed, setOfferConfirmed] = useState(false);
  const [signConfirmed, setSignConfirmed] = useState(false);
  const [confirmed, setConfirmed] = useState(false),
    [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    let loadedWriter: DraftWriter<Journey['application']> | null = null;
    writer.current?.dispose();
    writer.current = null;
    setSaving(0);
    setDraftError('');
    pendingSubmission.current = null;
    setSubmissionUncertain(false);
    setLoading(true);
    setError('');
    setNotice('');
    setJourney(null);
    setDocuments([]);
    setReplacements({});
    setConfirmed(false);
    setCounterConfirmed(false);
    setOfferConfirmed(false);
    setSignConfirmed(false);
    const load = async () => {
      if (applicationId) {
        const [result, docs, files] = await Promise.all([
          api<Journey>(`/applications/${applicationId}/journey`),
          api<Requirement[]>(`/applications/${applicationId}/requirements`),
          api<UploadedDocument[]>(`/applications/${applicationId}/documents`),
        ]);
        if (active) {
          loadedWriter = new DraftWriter(result.application, (current, payload) =>
            api<Journey['application']>(
              `/applications/${applicationId}`,
              { expectedVersion: current.rowVersion, answers: payload },
              'PATCH',
            ),
          );
          writer.current = loadedWriter;
          setJourney(result);
          setAnswers(result.application.answers);
          setRequirements(docs);
          setDocuments(files);
        }
      } else {
        const data = await api<{ content: Application[] }>('/applications?page=0&size=50');
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
      loadedWriter?.dispose();
    };
  }, [applicationId, refresh, attempt]);
  const set = (path: string, value: string | number | boolean | null) => {
    const [section, key] = path.split('.');
    setAnswers((old) => ({ ...old, [section]: { ...old[section], [key]: value } }));
    setNotice('');
    setConfirmed(false);
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
  const editable = journey && ['DRAFT', 'NEEDS_INFO'].includes(journey.application.status);
  const dirty = !!editable && !sameAnswers(journey.application.answers, answers);
  const save = async () => {
    const current = writer.current;
    if (!current || !applicationId) throw new Error('Заявка не загружена');
    if (pendingSubmission.current) throw new Error('Сначала проверьте результат отправки заявки.');
    setSaving((n) => n + 1);
    try {
      const updated = await current.save(answers);
      if (writer.current !== current) throw new Error('Эта форма уже закрыта.');
      setJourney((old) =>
        old?.application.id === updated.id ? { ...old, application: updated } : old,
      );
      setDraftError('');
      return updated;
    } catch (e) {
      if (writer.current === current)
        setDraftError(
          current.blocked
            ? 'Заявка изменена в другой вкладке. Загрузите актуальную версию, прежде чем продолжить.'
            : e instanceof Error
              ? e.message
              : 'Не удалось сохранить изменения.',
        );
      throw e;
    } finally {
      if (writer.current === current) setSaving((n) => Math.max(0, n - 1));
    }
  };
  useEffect(() => {
    if (loading || busy || !editable || !dirty || writer.current?.blocked || submissionUncertain)
      return;
    const timer = window.setTimeout(() => {
      void save().catch(() => undefined);
    }, 700);
    return () => window.clearTimeout(timer);
  }, [answers, loading, busy, applicationId, journey?.application.status, submissionUncertain]);

  useEffect(() => {
    if (!dirty) return;
    const protect = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', protect);
    return () => window.removeEventListener('beforeunload', protect);
  }, [dirty]);

  useEffect(() => {
    registerSave(
      editable
        ? async () => {
            await save();
          }
        : null,
    );
    return () => registerSave(null);
  }, [editable, answers, applicationId]);

  const perform = async (action: () => Promise<void>) => {
    if (acting.current) return;
    acting.current = true;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await action();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось выполнить действие');
    } finally {
      acting.current = false;
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
      let pending = pendingSubmission.current;
      if (!pending) {
        const draft = await save();
        pending = { id: draft.id, version: draft.rowVersion, key: crypto.randomUUID() };
        pendingSubmission.current = pending;
      }
      let submitted = false;
      try {
        await api(
          `/applications/${pending.id}/submit`,
          { expectedVersion: pending.version, confirmed: true },
          'POST',
          { 'Idempotency-Key': pending.key },
        );
        submitted = true;
        const updated = await api<Journey>(`/applications/${pending.id}/journey`);
        setJourney(updated);
        if (writer.current) writer.current.current = updated.application;
        pendingSubmission.current = null;
        setSubmissionUncertain(false);
        setNotice('Заявка отправлена. Статус рассмотрения появится в этом кабинете.');
      } catch (e) {
        if (!submitted && e instanceof ApiError && e.status > 0 && e.status < 500) {
          pendingSubmission.current = null;
          setSubmissionUncertain(false);
        } else {
          setSubmissionUncertain(true);
          setNotice(
            'Сервис не подтвердил результат. Повторите отправку: она будет проверена без создания дубликата.',
          );
        }
        throw e;
      }
    });
  const acceptCounteroffer = () =>
    void perform(async () => {
      const proposal = journey?.counteroffer;
      if (!applicationId || !proposal || !counterConfirmed) return;
      const updated = await api<Journey>(`/applications/${applicationId}/counteroffers/accept`, {
        proposalId: proposal.id,
        termsSha256: proposal.termsSha256,
        confirmed: true,
      });
      setJourney(updated);
      setCounterConfirmed(false);
      setNotice('Альтернативные условия приняты. Предложение сохранено в заявке.');
    });
  const product = products.find((p) => p.versionId === journey?.application.productVersionId);
  return (
    <section className="account-page">
      {applicationId && (
        <button
          className="back-link"
          onClick={() =>
            void perform(async () => {
              if (editable) await save();
              onOpen(null);
            })
          }
          disabled={busy}
        >
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
      {draftError && (
        <Banner tone="error">
          {draftError}{' '}
          <button
            className="text-action"
            disabled={busy || saving > 0}
            onClick={() => setAttempt((n) => n + 1)}
          >
            Загрузить актуальную версию
          </button>
        </Banner>
      )}
      {editable && (
        <p role="status" className="fine-print">
          {dirty
            ? saving > 0
              ? 'Сохраняем изменения…'
              : 'Есть несохранённые изменения…'
            : 'Все изменения сохранены автоматически.'}
        </p>
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
              {journey.counteroffer && journey.application.status === 'COUNTEROFFERED' && (
                <section className="application-overview" aria-label="Встречное предложение">
                  <h2>Встречное предложение</h2>
                  <p>Банк предлагает изменить условия вашей заявки:</p>
                  <p>Сумма: {money(journey.counteroffer.alternative_terms.amount)}</p>
                  <p>Срок: {journey.counteroffer.alternative_terms.termMonths} мес.</p>
                  <p>Ставка: {journey.counteroffer.alternative_terms.annualRatePct}% годовых</p>
                  <p>Действует до {date(journey.counteroffer.expiresAt)}</p>
                  {Date.parse(journey.counteroffer.expiresAt) <= Date.now() ? (
                    <Banner>Срок предложения истёк. Обновите статус заявки.</Banner>
                  ) : (
                    <>
                      <label className="confirmation">
                        <input
                          type="checkbox"
                          checked={counterConfirmed}
                          disabled={busy || externalBusy}
                          onChange={(e) => setCounterConfirmed(e.target.checked)}
                        />
                        Подтверждаю согласие с указанными суммой, сроком и ставкой
                      </label>
                      <Button
                        view="accent"
                        disabled={!counterConfirmed || busy || externalBusy}
                        onClick={acceptCounteroffer}
                      >
                        Принять условия
                      </Button>
                    </>
                  )}
                </section>
              )}
              {journey.offer && (
                <section className="application-overview" aria-label="Предложение банка">
                  <h2>Предложение банка</h2>
                  <p>
                    {money(journey.offer.terms.amount)} · {journey.offer.terms.termMonths} мес. ·{' '}
                    {journey.offer.terms.annualRatePct}% годовых
                  </p>
                  {journey.offer.response === 'ACCEPTED' && <p>Условия приняты</p>}
                  {journey.application.status === 'APPROVED' &&
                    journey.offer.response !== 'ACCEPTED' && (
                      <>
                        <p>Действует до {date(journey.offer.expiresAt)}</p>
                        <label className="confirmation">
                          <input
                            type="checkbox"
                            checked={offerConfirmed}
                            disabled={busy || externalBusy}
                            onChange={(e) => setOfferConfirmed(e.target.checked)}
                          />
                          Согласен с суммой, сроком и ставкой предложения
                        </label>
                        <Button
                          view="accent"
                          disabled={
                            !offerConfirmed ||
                            busy ||
                            externalBusy ||
                            Date.parse(journey.offer.expiresAt) <= Date.now()
                          }
                          onClick={() =>
                            void perform(async () => {
                              const updated = await api<Journey>(
                                `/applications/${applicationId}/offers/accept`,
                                { offerId: journey.offer!.id, confirmed: true },
                              );
                              setJourney(updated);
                              setOfferConfirmed(false);
                            })
                          }
                        >
                          Принять предложение
                        </Button>
                      </>
                    )}
                </section>
              )}
              {journey.application.status === 'OFFER_ACCEPTED' && journey.offer && (
                <section className="application-overview">
                  <h2>Демонстрационный договор</h2>
                  <p>
                    Сумма {money(journey.offer.terms.amount)}, срок {journey.offer.terms.termMonths}{' '}
                    мес., ставка {journey.offer.terms.annualRatePct}% годовых.
                  </p>
                  <p>Учебная операция: не является заключением реального кредитного договора.</p>
                  <label className="confirmation">
                    <input
                      type="checkbox"
                      checked={signConfirmed}
                      disabled={busy || externalBusy}
                      onChange={(e) => setSignConfirmed(e.target.checked)}
                    />
                    Подтверждаю условия и подписание демонстрационного договора
                  </label>
                  <Button
                    view="accent"
                    disabled={!signConfirmed || busy || externalBusy}
                    onClick={() =>
                      void perform(async () => {
                        setJourney(
                          await api<Journey>(`/applications/${applicationId}/contract/sign`, {
                            confirmed: true,
                          }),
                        );
                        setSignConfirmed(false);
                      })
                    }
                  >
                    Подписать демо-договор
                  </Button>
                </section>
              )}
              {journey.contracts?.map((contract) => (
                <Banner key={contract.id}>
                  Демо-договор {contract.contractNumber} подписан {date(contract.signedAt)}
                </Banner>
              ))}
              {journey.disbursements?.map((payment) => (
                <Banner tone="success" key={payment.id}>
                  Демонстрационная выдача: {money(payment.amount)} · {date(payment.executedAt)}
                </Banner>
              ))}
              <form
                className="application-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  submit();
                }}
              >
                <fieldset disabled={!editable || busy || externalBusy || submissionUncertain}>
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
                {submissionUncertain && (
                  <Button
                    view="secondary"
                    type="button"
                    disabled={busy || externalBusy}
                    onClick={submit}
                  >
                    Проверить отправку
                  </Button>
                )}
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
                          <fieldset
                            style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}
                            disabled={busy || externalBusy}
                          >
                            <Select
                              label={`Файл для замены: ${documentNames[doc.type_code] ?? doc.type_code}`}
                              value={replacements[doc.type_code] ?? ''}
                              options={{
                                '': 'Добавить отдельный документ',
                                ...Object.fromEntries(
                                  documents
                                    .filter(
                                      (file) => file.current && file.typeCode === doc.type_code,
                                    )
                                    .map((file) => [
                                      file.id,
                                      `${file.filename} · версия ${file.versionNo} · ${file.reviewResult === 'FAIL' ? 'отклонён' : file.reviewResult === 'PASS' ? 'проверен' : 'ожидает проверки'}`,
                                    ]),
                                ),
                              }}
                              onChange={(version) =>
                                setReplacements((old) => ({ ...old, [doc.type_code]: version }))
                              }
                            />
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
                                    if (replacements[doc.type_code])
                                      body.set('replacesVersionId', replacements[doc.type_code]);
                                    await save();
                                    await upload(`/applications/${applicationId}/documents`, body);
                                    const updated = await api<Journey>(
                                      `/applications/${applicationId}/journey`,
                                    );
                                    setJourney(updated);
                                    if (writer.current)
                                      writer.current.current = updated.application;
                                    const [updatedFiles, updatedRequirements] = await Promise.all([
                                      api<UploadedDocument[]>(
                                        `/applications/${applicationId}/documents`,
                                      ),
                                      api<Requirement[]>(
                                        `/applications/${applicationId}/requirements`,
                                      ),
                                    ]);
                                    setDocuments(updatedFiles);
                                    setRequirements(updatedRequirements);
                                    setReplacements((old) => ({ ...old, [doc.type_code]: '' }));
                                    setNotice('Документ загружен и ожидает проверки.');
                                  });
                                }}
                              />
                            </label>
                          </fieldset>
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
                  Для исправления выберите заменяемый файл; остальные документы сохранятся. PDF, PNG
                  или JPEG, до 10 МБ. Загрузка документа не означает, что он прошёл проверку.
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
                  onClick={() =>
                    void perform(async () => {
                      if (editable && !pendingSubmission.current) await save();
                      setAttempt((n) => n + 1);
                    })
                  }
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
