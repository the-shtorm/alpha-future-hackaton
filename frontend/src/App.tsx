import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Button } from '@alfalab/core-components-button';
import { Input } from '@alfalab/core-components-input';
import { Textarea } from '@alfalab/core-components-textarea';
import { api, ApiError, downloadJson } from './api';
import { emptyAnswers, exampleAnswers, normalizeAnswers } from './form';
import type {
  Answers,
  Candidate,
  Dictionaries,
  Packet,
  Party,
  Profile,
  Ranking,
  Reason,
} from './types';

const initialDictionaries: Dictionaries = {
  purposes: {
    WORKING_CAPITAL: 'Пополнение оборотных средств',
    CASH_GAP: 'Покрытие кассового разрыва',
    EQUIPMENT: 'Покупка оборудования',
    TRANSPORT: 'Покупка транспорта',
    COMMERCIAL_PROPERTY: 'Коммерческая недвижимость',
    CONTRACT_EXECUTION: 'Исполнение контракта',
    REFINANCING: 'Рефинансирование',
    DEVELOPMENT: 'Развитие бизнеса',
    INVESTMENT: 'Инвестиции',
  },
  sectors: {
    UNKNOWN: 'Не знаю',
    TRADE: 'Торговля',
    MANUFACTURING: 'Производство',
    SERVICES: 'Услуги',
    CONSTRUCTION: 'Строительство',
    TRANSPORT: 'Транспорт',
    AGRICULTURE: 'Сельское хозяйство',
    OTHER: 'Другая отрасль',
    GAMBLING: 'Азартные игры',
    FINANCIAL_ORGANIZATION: 'Финансовая организация',
  },
  usageModes: {
    ONE_TIME: 'Одной суммой',
    IN_PARTS: 'Частями по мере необходимости',
    ACCOUNT_RESERVE: 'Резерв на расчётном счёте',
    UNKNOWN: 'Пока не определились',
  },
  readiness: {
    YES: 'Готовы обсудить',
    NO: 'Не готовы',
    DISCUSS: 'Требуется обсуждение',
    UNKNOWN: 'Пока не знаем',
  },
};
const steps = ['О бизнесе', 'Задача и условия', 'Подбор предложений'];
const today = new Date().toISOString().slice(0, 10);

function Icon({ name, size = 22 }: { name: string; size?: number }) {
  const paths: Record<string, string> = {
    grid: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
    arrow: 'M5 12h14 M13 6l6 6-6 6',
    check: 'M5 12l4 4L19 6',
    brief: 'M3 7h18v14H3z M8 7V3h8v4 M3 12h18 M10 12v3h4v-3',
    file: 'M6 2h8l4 4v16H6z M14 2v5h5 M9 12h6 M9 16h6',
    shield: 'M12 2l8 4v6c0 5-8 10-8 10S4 17 4 12V6z M8 12l3 3 5-6',
    download: 'M12 3v12 M7 10l5 5 5-5 M4 16v5h16v-5',
    clock: 'M12 7v5l4 2 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name] ?? paths.file} />
    </svg>
  );
}

export function App() {
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<Answers>(() => structuredClone(emptyAnswers));
  const [token, setToken] = useState(''); // Session stays in memory; financial form is never written to browser storage.
  const [parties, setParties] = useState<Party[]>([]);
  const [party, setParty] = useState('');
  const [dict, setDict] = useState(initialDictionaries);
  const [loginOpen, setLoginOpen] = useState(false);
  const [pendingResume, setPendingResume] = useState<{ profileId: string; runId: string } | null>(
    null,
  );
  const modal = useRef<HTMLElement>(null);
  const [login, setLogin] = useState('demo-owner');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [help, setHelp] = useState(false);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [packet, setPacket] = useState<Packet | null>(null);
  const [ranking, setRanking] = useState<Ranking | null>(null);
  const [excluded, setExcluded] = useState<{ productCode: string; reasons: Reason[] }[]>([]);
  const [reply, setReply] = useState('');
  const [chosen, setChosen] = useState('');
  const [isExample, setIsExample] = useState(false);

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' });
  }, [step]);

  useEffect(() => {
    if (!loginOpen) return;
    const previous = document.activeElement as HTMLElement | null;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) {
        setLoginOpen(false);
        setPassword('');
      }
      if (event.key !== 'Tab') return;
      const nodes = modal.current?.querySelectorAll<HTMLElement>(
        'button:not(:disabled), input:not(:disabled), select, textarea, a[href]',
      );
      if (!nodes?.length) return;
      const first = nodes[0],
        last = nodes[nodes.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      previous?.focus();
    };
  }, [loginOpen, busy]);

  const resume = async (auth: string, ids: { profileId: string; runId: string }) => {
    const saved = await api<Profile>(`/selection-profiles/${ids.profileId}`, auth);
    const route = `/selection-profiles/${ids.profileId}/recommendations/${ids.runId}`;
    const data = await api<Packet>(`${route}/ranking-export`, auth);
    const checks = await api<{
      items: { productCode: string; status: string; reasons: Reason[] }[];
    }>(route, auth);
    let result: Ranking | null = null;
    try {
      result = await api<Ranking>(`${route}/ranking-result`, auth);
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 404)) throw e;
    }
    setAnswers({ ...structuredClone(emptyAnswers), ...saved.answers });
    setProfile(saved);
    setParty(saved.partyId);
    setPacket(data);
    setRanking(result);
    setExcluded(checks.items.filter((i) => i.status === 'INELIGIBLE'));
    setChosen(saved.selectedRunId === ids.runId ? (saved.selectedProductVersionId ?? '') : '');
    setReply('');
    setIsExample(false);
    setStep(2);
    setPendingResume(null);
    setNotice('Подбор восстановлен по данным сервера. Можно загрузить ответ команды.');
  };

  const setValue = (path: string, value: string | number | boolean | null) => {
    const [section, key] = path.split('.');
    setAnswers((old) => ({ ...old, [section]: { ...old[section], [key]: value } }));
    setPacket(null);
    setRanking(null);
    setChosen('');
    setNotice('');
    setError('');
  };
  const value = (path: string) => {
    const [s, k] = path.split('.');
    return answers[s]?.[k] ?? '';
  };
  const field = (
    path: string,
    label: string,
    type: 'text' | 'number' | 'date' = 'text',
    required = false,
    hint?: string,
  ) =>
    type === 'date' ? (
      <label className="native-date" key={path}>
        <span>
          {label}
          {required ? ' *' : ''}
        </span>
        <input
          type="date"
          aria-label={label}
          value={String(value(path))}
          required={required}
          max={today}
          onChange={(e) => setValue(path, e.target.value)}
        />
      </label>
    ) : (
      <div className="field" key={path}>
        <Input
          id={path}
          label={label}
          type={type}
          block
          size={56}
          value={String(value(path))}
          required={required}
          hint={hint}
          autoComplete="off"
          {...(type === 'number'
            ? { min: path === 'request.termMonths' ? 1 : 0, max: 1200, step: 1 }
            : {})}
          onChange={(event) =>
            setValue(
              path,
              type === 'number'
                ? event.target.value === ''
                  ? null
                  : Number(event.target.value)
                : event.target.value,
            )
          }
        />
      </div>
    );
  const select = (
    path: string,
    label: string,
    options: Record<string, string>,
    required = false,
  ) => (
    <label className="select-field" key={path}>
      <span>
        {label}
        {required ? ' *' : ''}
      </span>
      <select
        aria-label={label}
        value={String(value(path))}
        onChange={(e) => setValue(path, e.target.value)}
        required={required}
      >
        {Object.entries(options).map(([key, text]) => (
          <option key={key} value={key}>
            {text}
          </option>
        ))}
      </select>
      <span className="select-chevron" aria-hidden="true">
        ⌄
      </span>
    </label>
  );
  const attempt = async (action: () => Promise<void>) => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await action();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось выполнить запрос');
    } finally {
      setBusy(false);
    }
  };
  const authenticate = (event: FormEvent) => {
    event.preventDefault();
    void attempt(async () => {
      const session = await api<{ accessToken: string }>('/auth/login', '', { login, password });
      // Store token immediately so a later /me failure still allows an explicit logout.
      setToken(session.accessToken);
      setPassword('');
      const [me, dictionaries] = await Promise.all([
        api<{ parties: Party[] }>('/me', session.accessToken),
        api<Dictionaries>('/forms/preliminary/dictionaries', session.accessToken),
      ]);
      const writable = me.parties.filter(
        (p) => p.access_role === 'OWNER' || p.access_role === 'EDITOR',
      );
      setParties(writable);
      setParty(writable[0]?.id ?? '');
      setDict(dictionaries);
      setLoginOpen(false);
      if (!writable.length)
        throw new Error('У этого пользователя нет компаний с правом заполнения формы');
      if (pendingResume) await resume(session.accessToken, pendingResume);
    });
  };
  const logout = () =>
    void attempt(async () => {
      await api('/auth/logout', token, {});
      setToken('');
      setParties([]);
      setParty('');
      setProfile(null);
      setPacket(null);
      setRanking(null);
      setChosen('');
      setReply('');
      setPendingResume(null);
      setStep(0);
      setAnswers(structuredClone(emptyAnswers));
      setIsExample(false);
    });
  const checkForm = () => {
    if (!token) {
      setLoginOpen(true);
      return;
    }
    if (!party) {
      setError('Выберите компанию');
      return;
    }
    void attempt(async () => {
      const saved = await api<Profile>('/selection-profiles', token, {
        partyId: party,
        answers: normalizeAnswers(answers),
      });
      setProfile(saved);
      const run = await api<{
        runId: string;
        items: { productCode: string; status: string; reasons: Reason[] }[];
      }>(`/selection-profiles/${saved.id}/eligibility`, token, {});
      setExcluded(run.items.filter((i) => i.status === 'INELIGIBLE'));
      const data = await api<Packet>(
        `/selection-profiles/${saved.id}/recommendations/${run.runId}/ranking-export`,
        token,
      );
      setPacket(data);
      setRanking(null);
      setChosen('');
      setReply('');
      setStep(2);
    });
  };
  const importRanking = () =>
    void attempt(async () => {
      if (!packet || !profile) return;
      let parsed: unknown;
      try {
        parsed = JSON.parse(reply);
      } catch {
        throw new Error('Проверьте JSON: файл должен содержать ответ команды ранжирования');
      }
      const data = await api<Ranking>(
        `/selection-profiles/${profile.id}/recommendations/${packet.requestId}/ranking-result`,
        token,
        parsed,
      );
      setRanking(data);
      window.scrollTo({ top: 0, behavior: 'instant' });
      setNotice('Ответ загружен. Порядок обновлён, предупреждения сохранены.');
    });
  const chooseProduct = (candidate: Candidate) =>
    void attempt(async () => {
      if (!packet || !profile) return;
      const updated = await api<Profile>(
        `/selection-profiles/${profile.id}/selected-product`,
        token,
        {
          expectedVersion: profile.rowVersion,
          runId: packet.requestId,
          productVersionId: candidate.productVersion,
        },
        'PUT',
      );
      setProfile(updated);
      setChosen(candidate.productVersion);
      setNotice('Продукт выбран. Полная заявка — следующий отдельный этап.');
    });
  const fillExample = () => {
    setAnswers(exampleAnswers());
    setProfile(null);
    setPacket(null);
    setRanking(null);
    setChosen('');
    setIsExample(true);
    setNotice('Заполнены синтетические данные примера. Их можно изменить.');
    setError('');
    setStep(0);
  };
  const candidates = ranking?.results ?? packet?.candidates ?? [];
  const amount = Number(value('request.amount'));
  const title =
    step === 2 ? 'Предложения для вашего бизнеса' : 'Финансирование под\nзадачи вашего бизнеса';

  return (
    <div className="app">
      <a className="skip-link" href="#content">
        К содержимому
      </a>
      <header className="topbar">
        <div className="wordmark">
          <span className="alpha-letter" aria-hidden="true">
            А
          </span>
          <span>
            Альфа-Банк<small>Бизнес · прототип</small>
          </span>
        </div>
        <div className="header-right">
          <span className="prototype">Хакатонный проект</span>
          <button className="help-link" onClick={() => setHelp(!help)}>
            Помощь <span>?</span>
          </button>
          <Button
            size={40}
            view="secondary"
            onClick={token ? logout : () => setLoginOpen(true)}
            disabled={busy}
          >
            {token ? 'Выйти' : 'Войти в кабинет'}
          </Button>
        </div>
      </header>
      <div className="workspace">
        <aside className="sidebar">
          <p className="workspace-label">ВАШ БИЗНЕС</p>
          <div className="active-nav">
            <Icon name="brief" /> Финансирование <span>→</span>
          </div>
          <div className="sidebar-route">
            <p>ПОДБОР КРЕДИТА</p>
            {steps.map((name, index) => (
              <div
                className={`route-step ${step === index ? 'current' : ''} ${step > index ? 'completed' : ''}`}
                key={name}
              >
                <span>{step > index ? <Icon name="check" size={14} /> : index + 1}</span>
                <div>
                  {name}
                  <small>
                    {index === 0
                      ? 'Компания и выручка'
                      : index === 1
                        ? 'Потребность в деньгах'
                        : 'Проверка и рекомендации'}
                  </small>
                </div>
              </div>
            ))}
          </div>
          <div className="sidebar-bottom">
            <Icon name="shield" />
            <p>
              Вы управляете данными
              <small>Передача команде — только после скачивания вами файла.</small>
            </p>
          </div>
        </aside>
        <main id="content">
          <div className="breadcrumbs">
            Бизнес <span>/</span> Финансирование <span>/</span> Подбор кредита
          </div>
          <div className="intro">
            <div>
              <span className="eyebrow">ФИНАНСИРОВАНИЕ БИЗНЕСА</span>
              <h1>
                {title.split('\n').map((line, i) => (
                  <span key={i}>
                    {line}
                    <br />
                  </span>
                ))}
              </h1>
              <p>
                {step === 2
                  ? ranking
                    ? 'Сохранили порядок команды и условия применимости. Выберите подходящий продукт.'
                    : 'Проверили ограничения продуктов. Следующий шаг — получить порядок рекомендаций от команды.'
                  : 'Расскажите о компании и цели. Проверим условия продуктов\nи подготовим данные для персонального подбора.'}
              </p>
            </div>
            <div className="intro-note">
              <span className="mini-dot" />{' '}
              {step === 2 ? 'Проверка завершена' : 'Предварительный подбор'}
              <small>
                {step === 2 ? `${candidates.length} доступных вариантов` : 'Без подачи заявки'}
              </small>
            </div>
          </div>
          {help && (
            <div className="notice info" role="status">
              Заполните форму → проверьте ограничения → скачайте JSON → передайте файл вашей команде
              → загрузите её ответ. Продукты в каталоге синтетические. Проверка и сходство не
              означают одобрение кредита.
            </div>
          )}
          {error && (
            <div className="notice error" role="alert">
              {error}
            </div>
          )}
          {notice && (
            <div className="notice info" role="status">
              {notice}
            </div>
          )}
          {step === 0 && (
            <label className="resume-control">
              Уже передавали данные команде? <span>Продолжить подбор из файла ↗</span>
              <input
                type="file"
                accept=".json,application/json"
                aria-label="Восстановить подбор из экспортированного JSON"
                disabled={busy}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  e.target.value = '';
                  if (!file) return;
                  void attempt(async () => {
                    if (file.size > 1024 * 1024)
                      throw new Error('Пакет должен быть не больше 1 МБ');
                    let data: Packet;
                    try {
                      data = JSON.parse(await file.text());
                    } catch {
                      throw new Error('Нужен JSON ранее скачанного пакета');
                    }
                    const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
                    if (
                      data.schemaVersion !== 'query-passage-mvp-1' ||
                      !uuid.test(data.profileId) ||
                      !uuid.test(data.requestId)
                    )
                      throw new Error('В файле нет идентификаторов экспортированного подбора');
                    const ids = { profileId: data.profileId, runId: data.requestId };
                    if (!token) {
                      setPendingResume(ids);
                      setLoginOpen(true);
                    } else await resume(token, ids);
                  });
                }}
              />
            </label>
          )}
          <div className="content-grid">
            <div className="primary-column">
              {step < 2 ? (
                <form
                  className="form-panel"
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (step === 0) {
                      setStep(1);
                      setError('');
                    } else checkForm();
                  }}
                >
                  <fieldset disabled={busy} className="form-fields">
                    <div className="panel-heading">
                      <div className="step-icon">
                        <Icon name={step === 0 ? 'brief' : 'file'} />
                      </div>
                      <div>
                        <span className="overline">ШАГ {step + 1} ИЗ 3</span>
                        <h2>{step === 0 ? 'Расскажите о бизнесе' : 'На что нужны деньги'}</h2>
                      </div>
                      {isExample && <span className="badge neutral">Пример</span>}
                    </div>
                    {step === 0 ? (
                      <>
                        {token && (
                          <label className="company-select">
                            Компания
                            <select
                              aria-label="Компания"
                              value={party}
                              onChange={(e) => {
                                setParty(e.target.value);
                                setProfile(null);
                                setPacket(null);
                                setRanking(null);
                                setChosen('');
                              }}
                            >
                              {parties.map((p) => (
                                <option key={p.id} value={p.id}>
                                  {p.name}
                                </option>
                              ))}
                            </select>
                          </label>
                        )}
                        <div className="segmented" role="group" aria-label="Форма бизнеса">
                          {[
                            ['LLC', 'ООО'],
                            ['IP', 'ИП'],
                          ].map(([key, text]) => (
                            <button
                              type="button"
                              aria-pressed={value('registration.borrowerKind') === key}
                              onClick={() => setValue('registration.borrowerKind', key)}
                              key={key}
                            >
                              {text}
                            </button>
                          ))}
                        </div>
                        <div className="fields-grid">
                          {select('business.sector', 'Сфера деятельности', dict.sectors)}
                          {select('business.taxRegime', 'Система налогообложения', {
                            UNKNOWN: 'Не знаю',
                            USN: 'УСН',
                            OSNO: 'ОСНО',
                            AUSN: 'АУСН',
                            ...(value('registration.borrowerKind') === 'IP'
                              ? { PSN: 'Патент', NPD: 'НПД' }
                              : {}),
                            COMBINED: 'Совмещённая',
                            OTHER: 'Другая',
                          })}
                          {field('registration.registeredOn', 'Дата регистрации', 'date', true)}
                          {field('business.actualStartedOn', 'Начало деятельности', 'date', true)}
                          {field(
                            'financial.revenue',
                            'Выручка за период, ₽',
                            'text',
                            true,
                            'Сумма в рублях, например 24000000.00',
                          )}
                          <label className="select-field">
                            <span>Компания в реестре МСП</span>
                            <select
                              aria-label="Компания в реестре МСП"
                              value={
                                value('business.mspRegistry') === ''
                                  ? ''
                                  : String(value('business.mspRegistry'))
                              }
                              onChange={(e) =>
                                setValue(
                                  'business.mspRegistry',
                                  e.target.value === '' ? null : e.target.value === 'true',
                                )
                              }
                            >
                              <option value="">Не знаю</option>
                              <option value="true">Да</option>
                              <option value="false">Нет</option>
                            </select>
                            <span className="select-chevron" aria-hidden="true">
                              ⌄
                            </span>
                          </label>
                          {field('financial.periodFrom', 'Начало периода выручки', 'date', true)}
                          {field('financial.periodTo', 'Конец периода выручки', 'date', true)}
                          {value('registration.borrowerKind') === 'IP' &&
                            field('business.ipAgeYears', 'Возраст предпринимателя, лет', 'number')}
                        </div>
                        <details className="extra-fields">
                          <summary>
                            Регион и специальные условия <span>Необязательно</span>
                          </summary>
                          <div className="fields-grid">
                            {field('registration.country', 'Код страны, например RU')}
                            {field('business.region', 'Код региона, например 77')}
                            {field(
                              'business.bankAccountMonths',
                              'Стаж расчётного счёта, мес.',
                              'number',
                            )}
                            {field(
                              'business.marketplaceMonths',
                              'Продажи на маркетплейсе, мес.',
                              'number',
                            )}
                          </div>
                        </details>
                      </>
                    ) : (
                      <>
                        <div className="fields-grid">
                          {select('request.purpose', 'Цель финансирования', dict.purposes, true)}
                          {select(
                            'request.usageMode',
                            'Как будете использовать деньги',
                            dict.usageModes,
                            true,
                          )}
                          {field(
                            'request.amount',
                            'Сумма финансирования, ₽',
                            'text',
                            true,
                            'Для кредитной линии — размер лимита',
                          )}
                          {field('request.termMonths', 'Срок финансирования, мес.', 'number', true)}
                        </div>
                        <div className="description-field">
                          <Textarea
                            label="Расскажите о задаче"
                            id="request-description"
                            block
                            maxLength={500}
                            minRows={3}
                            value={String(value('request.description'))}
                            hint={`${String(value('request.description')).length}/500 · Необязательно, без персональных данных`}
                            placeholder="Например, закупаем товар небольшими партиями перед сезоном"
                            onChange={(event) =>
                              setValue('request.description', event.target.value)
                            }
                          />
                        </div>
                        <h3 className="section-title">Обеспечение</h3>
                        <p className="muted small">
                          Ответ показывает готовность к обсуждению. Наличие залога или поручителя
                          пока не подтверждается.
                        </p>
                        <div className="fields-grid">
                          {select(
                            'security.collateralReady',
                            'Имущественный залог',
                            dict.readiness,
                          )}
                          {select('security.guarantorReady', 'Поручительство', dict.readiness)}
                        </div>
                      </>
                    )}
                    <div className="form-footer">
                      {step === 0 ? (
                        <button type="button" className="text-button" onClick={fillExample}>
                          Заполнить пример
                        </button>
                      ) : (
                        <Button
                          view="transparent"
                          size={48}
                          type="button"
                          onClick={() => setStep(0)}
                        >
                          ← Назад
                        </Button>
                      )}
                      <Button
                        type="submit"
                        view="accent"
                        size={56}
                        loading={busy}
                        rightAddons={<Icon name="arrow" size={20} />}
                      >
                        {step === 0 ? 'Продолжить' : 'Проверить форму'}
                      </Button>
                    </div>
                  </fieldset>
                </form>
              ) : (
                <>
                  <div className="quick-exchange">
                    <div>
                      <strong>Передайте подбор команде</strong>
                      <p>Пакет содержит проверенную форму и допустимые продукты</p>
                    </div>
                    <Button
                      view="secondary"
                      size={40}
                      disabled={!packet || !candidates.length}
                      onClick={() =>
                        packet && downloadJson(`ranking-request-${packet.requestId}.json`, packet)
                      }
                    >
                      Скачать JSON
                    </Button>
                    <a href="#ranking-exchange">Загрузить ответ ↓</a>
                  </div>
                  <div className="results-toolbar">
                    <div>
                      <span className="badge neutral">{candidates.length} вариантов</span>{' '}
                      <span className="small muted">
                        {ranking ? 'Порядок от команды' : 'Ожидаем ранжирование'}
                      </span>
                    </div>
                    <button className="text-button" onClick={() => setStep(0)}>
                      Изменить форму
                    </button>
                  </div>
                  {!candidates.length && (
                    <div className="form-panel empty-state">
                      <Icon name="file" size={38} />
                      <h2>Подходящих продуктов пока нет</h2>
                      <p>
                        Посмотрите причины исключения ниже. Можно скорректировать потребность и
                        повторить проверку.
                      </p>
                      <Button view="secondary" onClick={() => setStep(1)}>
                        Изменить условия
                      </Button>
                    </div>
                  )}
                  {candidates.map((candidate, index) => (
                    <article
                      className={`product-card ${candidate.isRecommended ? 'recommended' : ''}`}
                      key={candidate.productVersion}
                    >
                      <div className="card-top">
                        <span className="product-number">{String(index + 1).padStart(2, '0')}</span>
                        {candidate.isRecommended && (
                          <span className="badge recommended-badge">По вашему запросу</span>
                        )}
                        <span
                          className={`badge ${candidate.eligibilityStatus === 'CONDITIONAL' ? 'warning' : 'success'}`}
                        >
                          {candidate.eligibilityStatus === 'CONDITIONAL'
                            ? 'Есть условия для уточнения'
                            : 'Ограничения пройдены'}
                        </span>
                        <span className="small muted">{candidate.product.code}</span>
                      </div>
                      <h2>{candidate.product.name}</h2>

                      {candidate.similarityScore !== undefined && (
                        <div className="similarity">
                          <strong>{candidate.similarityScore.toFixed(4)}</strong>
                          <span>
                            Техническое сходство<small>Не вероятность одобрения</small>
                          </span>
                        </div>
                      )}
                      {candidate.pendingConditions.length > 0 && (
                        <div className="product-warnings">
                          <Icon name="shield" size={18} />
                          <div>
                            <strong>Что нужно уточнить</strong>
                            <ul>
                              {candidate.pendingConditions.map((reason, i) => (
                                <li key={`${reason.code}-${i}`}>{reason.message}</li>
                              ))}
                            </ul>
                          </div>
                        </div>
                      )}
                      <div className="card-footer">
                        <span className="small muted">Синтетический продукт · DEMO</span>
                        <Button
                          view={chosen === candidate.productVersion ? 'secondary' : 'primary'}
                          size={40}
                          disabled={busy || chosen !== ''}
                          onClick={() => chooseProduct(candidate)}
                        >
                          {chosen === candidate.productVersion ? 'Выбрано' : 'Выбрать продукт'}
                        </Button>
                      </div>
                    </article>
                  ))}
                  {excluded.length > 0 && (
                    <details className="excluded">
                      <summary>Не прошли ограничения: {excluded.length}</summary>
                      {excluded.map((p) => (
                        <div key={p.productCode}>
                          <strong>{p.productCode}</strong>
                          <ul>
                            {p.reasons
                              .filter((r) => r.result === 'FAIL')
                              .map((r, i) => (
                                <li key={i}>
                                  {r.message} <code>{r.code}</code>
                                </li>
                              ))}
                          </ul>
                        </div>
                      ))}
                    </details>
                  )}
                  {!!candidates.length && packet && (
                    <section className="exchange-panel" id="ranking-exchange">
                      <span className="overline">РАБОТА С КОМАНДОЙ</span>
                      <h2>Передайте данные на ранжирование</h2>
                      <p className="muted">
                        Скачайте JSON и отправьте коллегам самостоятельно. Когда получите ответ,
                        загрузите его сюда.
                      </p>
                      <Button
                        view="secondary"
                        size={48}
                        leftAddons={<Icon name="download" size={18} />}
                        onClick={() =>
                          downloadJson(`ranking-request-${packet.requestId}.json`, packet)
                        }
                      >
                        Скачать пакет JSON
                      </Button>
                      <button
                        className="text-button template-download"
                        onClick={() =>
                          downloadJson(`ranking-response-template-${packet.requestId}.json`, {
                            requestId: packet.requestId,
                            metadata: {
                              model: 'REPLACE_WITH_MODEL_NAME',
                              modelVersion: 'REPLACE_WITH_MODEL_VERSION',
                              queryTemplateVersion: 'REPLACE_WITH_QUERY_TEMPLATE_VERSION',
                              passageTemplateVersion: 'REPLACE_WITH_PASSAGE_TEMPLATE_VERSION',
                            },
                            results: packet.candidates.map((c, i) => ({
                              productId: c.productId,
                              productVersion: c.productVersion,
                              rank: i + 1,
                              similarityScore: null,
                              isRecommended: i < Math.min(packet.topK, 3),
                              eligibilityStatus: c.eligibilityStatus,
                              pendingConditions: c.pendingConditions,
                            })),
                          })
                        }
                      >
                        Шаблон ответа для команды
                      </button>
                      <details className="contract-preview">
                        <summary>Что входит в пакет</summary>
                        <p>
                          Проверенная форма, допустимые версии продуктов, словари и предупреждения.
                          Полная заявка и её финансовые признаки в подбор не попадают.
                        </p>
                        <code>requestId: {packet.requestId}</code>
                      </details>
                      <label className="file-label">
                        Загрузить ответ из JSON-файла
                        <input
                          aria-label="Ответ команды, JSON-файл"
                          type="file"
                          accept=".json,application/json"
                          disabled={busy || !!ranking}
                          onChange={async (e) => {
                            const file = e.target.files?.[0];
                            e.target.value = '';
                            if (!file) return;
                            if (file.size > 1024 * 1024) {
                              setError('Ответ должен быть не больше 1 МБ');
                              return;
                            }
                            try {
                              setReply(await file.text());
                              setError('');
                            } catch {
                              setError('Не удалось прочитать файл');
                            }
                          }}
                        />
                      </label>
                      <Textarea
                        label="Или вставьте ответ JSON"
                        block
                        minRows={4}
                        maxLength={1048576}
                        value={reply}
                        disabled={!!ranking}
                        onChange={(e) => setReply(e.target.value)}
                      />
                      <div className="import-footer">
                        <span className="small muted">
                          Нужны идентификаторы, порядок и сходство
                        </span>
                        <Button
                          view="accent"
                          size={48}
                          loading={busy}
                          disabled={!reply.trim() || !!ranking}
                          onClick={importRanking}
                        >
                          {ranking ? 'Ответ сохранён' : 'Применить ответ'}
                        </Button>
                      </div>
                    </section>
                  )}
                </>
              )}
            </div>
            <aside className="context-column">
              <div className="context-card">
                <div className="context-icon">
                  <Icon name="grid" size={24} />
                </div>
                <h3>
                  От задачи —<br />к подходящему продукту
                </h3>
                <p>
                  Сначала проверим ограничения, затем получим рекомендации по вашей потребности.
                </p>
                <ol>
                  {[
                    'Проверка условий продукта',
                    'Передача данных команде',
                    'Загрузка рекомендаций',
                  ].map((text, i) => (
                    <li key={text}>
                      <span>{i + 1}</span>
                      {text}
                    </li>
                  ))}
                </ol>
              </div>
              <div className="request-summary">
                <span className="overline">ВАША ПОТРЕБНОСТЬ</span>
                <h3>
                  {amount > 0
                    ? `${new Intl.NumberFormat('ru-RU').format(amount)} ₽`
                    : 'Начнём с вашей задачи'}
                </h3>
                <p>{dict.purposes[String(value('request.purpose'))]}</p>
                <div>
                  <span>Срок</span>
                  <strong>{String(value('request.termMonths'))} мес.</strong>
                </div>
                <div>
                  <span>Использование</span>
                  <strong>{dict.usageModes[String(value('request.usageMode'))]}</strong>
                </div>
              </div>
              <div className="disclaimer">
                <Icon name="shield" size={18} />
                <p>
                  Предварительная проверка и техническое сходство не гарантируют одобрение. Условия
                  каталога — демонстрационные.
                </p>
              </div>
            </aside>
          </div>
          <footer className="page-footer">
            <span>Хакатонный прототип · {new Date().getFullYear()}</span>
            <a
              href="https://core-ds.github.io/core-components/master/?path=/docs/intro--docs"
              target="_blank"
              rel="noreferrer"
            >
              На основе Core Components ↗
            </a>
          </footer>
        </main>
      </div>
      {loginOpen && (
        <div className="modal-overlay">
          <section
            className="login-modal"
            ref={modal}
            role="dialog"
            aria-modal="true"
            aria-labelledby="login-title"
          >
            <button
              aria-label="Закрыть вход"
              className="modal-close"
              disabled={busy}
              onClick={() => {
                setLoginOpen(false);
                setPassword('');
              }}
            >
              ×
            </button>
            <span className="eyebrow">КАБИНЕТ БИЗНЕСА</span>
            <h2 id="login-title">Войти для проверки формы</h2>
            <p className="muted">
              Используйте аккаунт backend. Пароль DEMO задаётся при запуске сервера.
            </p>
            <form onSubmit={authenticate}>
              <Input
                block
                label="Логин"
                autoComplete="username"
                value={login}
                onChange={(e) => setLogin(e.target.value)}
                required
                autoFocus
              />
              <Input
                block
                type="password"
                label="Пароль"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
              {error && (
                <p role="alert" className="login-error">
                  {error}
                </p>
              )}
              <Button block type="submit" view="accent" size={56} loading={busy}>
                Войти
              </Button>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}
