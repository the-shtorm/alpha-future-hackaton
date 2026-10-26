import { useEffect, useRef, useState, type FormEvent } from 'react';
import { api, ApiError, clearApiSession } from './api';
import { readView, viewSearch, type Page } from './view';
import { emptyAnswers, normalizeAnswers, sameAnswers } from './form';
import { browserDraftStorage, readGuestDraft, writeGuestDraft, clearGuestDraft } from './drafts';
import { dictionaries } from './presentation';
import { CatalogPage, ProductDetails } from './components/Catalog';
import { SelectionResults, SavedSelections } from './components/Selections';
import { Wizard } from './components/Wizard';
import { ApplicationsPage } from './components/Applications';
import { BankPage } from './components/Bank';
import { Banner, Button, Icon, Modal } from './components/UI';
import { Input } from '@alfalab/core-components-input';
import type {
  Answers,
  Candidate,
  Dictionaries,
  Party,
  Product,
  Profile,
  SavedSelection,
  Selection,
  SelectionAlternative,
} from './types';

type Intent = 'submit' | 'saved' | 'applications' | null;

export function App() {
  const [page, setPage] = useState<Page>('catalog');
  const [products, setProducts] = useState<Product[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState('');
  const [catalogAttempt, setCatalogAttempt] = useState(0);
  const [details, setDetails] = useState<Product | null>(null);
  const [answers, setAnswers] = useState<Answers>(
    () => readGuestDraft(browserDraftStorage()) ?? structuredClone(emptyAnswers),
  );
  const [dictionary, setDictionary] = useState<Dictionaries>(dictionaries);
  const [authenticated, setAuthenticated] = useState(false);
  const [bankApprover, setBankApprover] = useState(false);
  const [restoring, setRestoring] = useState(true);
  const [sessionAttempt, setSessionAttempt] = useState(0);
  const [draftNotice, setDraftNotice] = useState('');
  const [sessionError, setSessionError] = useState('');
  const sessionGeneration = useRef(0);
  const profileRef = useRef<Profile | null>(null);
  const saveQueue = useRef<Promise<unknown>>(Promise.resolve());
  const saveConflict = useRef(false);
  const channel = useRef<BroadcastChannel | null>(null);
  const acting = useRef(false);
  const applicationSave = useRef<(() => Promise<void>) | null>(null);
  const [displayName, setDisplayName] = useState('');
  const [parties, setParties] = useState<Party[]>([]);
  const [partyId, setPartyId] = useState('');
  const [profile, setProfile] = useState<Profile | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [saved, setSaved] = useState<SavedSelection[]>([]);
  const [applicationId, setApplicationId] = useState<string | null>(null);
  const [applicationRefresh, setApplicationRefresh] = useState(0);
  const [loginOpen, setLoginOpen] = useState(false);
  const [intent, setIntent] = useState<Intent>(null);
  const [login, setLogin] = useState('');
  const [password, setPassword] = useState('');
  const [loginError, setLoginError] = useState('');
  const [error, setError] = useState('');
  const [working, setBusy] = useState(false);
  const busy = working || restoring;
  const writable = parties.filter((p) => ['OWNER', 'EDITOR'].includes(p.access_role));

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' });
  }, [page]);
  useEffect(() => {
    let active = true;
    setCatalogLoading(true);
    setCatalogError('');
    api<{ content: Product[] }>('/products?page=0&size=50')
      .then((data) => {
        if (active) setProducts(data.content);
      })
      .catch((e) => {
        if (active) setCatalogError(e.message);
      })
      .finally(() => {
        if (active) setCatalogLoading(false);
      });
    return () => {
      active = false;
    };
  }, [catalogAttempt]);

  function clearProtected(keepGuest = false) {
    sessionGeneration.current++;
    profileRef.current = null;
    saveConflict.current = false;
    setAuthenticated(false);
    setBankApprover(false);
    setDisplayName('');
    setParties([]);
    setPartyId('');
    setProfile(null);
    setSelection(null);
    setSaved([]);
    setApplicationId(null);
    if (!keepGuest) clearGuestDraft(browserDraftStorage());
    setAnswers(
      (keepGuest ? readGuestDraft(browserDraftStorage()) : null) ?? structuredClone(emptyAnswers),
    );
    setDraftNotice('');
    setPassword('');
    setIntent(null);
    setPage('catalog');
    clearApiSession();
  }

  useEffect(() => {
    let active = true;
    const view = readView(window.location.search);
    setRestoring(true);
    setSessionError('');
    const restore = async () => {
      let me: { user: { display_name: string }; parties: Party[]; bankApprover?: boolean };
      try {
        me = await api('/me');
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) {
          if (active) {
            clearProtected(true);
            if (view.page === 'form' && !view.profileId) setPage('form');
          }
          return;
        }
        throw e;
      }
      const dict = await api<Dictionaries>('/forms/preliminary/dictionaries');
      if (!active) return;
      setAuthenticated(true);
      setBankApprover(me.bankApprover === true);
      setDisplayName(me.user.display_name);
      setParties(me.parties);
      setDictionary(dict);
      setPartyId(me.parties.find((p) => ['OWNER', 'EDITOR'].includes(p.access_role))?.id ?? '');
      try {
        if (['form', 'results'].includes(view.page) && view.profileId) {
          const p = await api<Profile>(`/selection-profiles/${view.profileId}`);
          if (!active) return;
          profileRef.current = p;
          saveConflict.current = false;
          setProfile(p);
          setPartyId(p.partyId);
          setAnswers(normalizeAnswers(p.answers));
          setPage('form');
          if (view.page === 'results' && view.runId) {
            const result = await api<Selection>(
              `/selection-profiles/${p.id}/recommendations/${view.runId}/view`,
            );
            if (!active) return;
            setSelection(result);
            setPage('results');
          }
        } else if (view.page === 'saved') {
          const data = await api<{ items: SavedSelection[] }>('/selections');
          if (!active) return;
          setSaved(data.items);
          setPage('saved');
        } else if (view.page === 'bank' && me.bankApprover) {
          setPage('bank');
        } else if (view.page === 'applications') {
          setApplicationId(view.applicationId);
          setPage('applications');
        } else {
          if (view.page === 'form') {
            const guest = readGuestDraft(browserDraftStorage());
            const company = me.parties.find((p) => ['OWNER', 'EDITOR'].includes(p.access_role));
            if (guest)
              setAnswers({
                ...guest,
                registration: {
                  ...guest.registration,
                  ...(company ? { borrowerKind: company.party_kind } : {}),
                },
              });
          }
          setPage(view.page === 'form' ? 'form' : 'catalog');
        }
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : 'Не удалось восстановить страницу.');
      }
    };
    void restore()
      .catch((e) => {
        if (active)
          setSessionError(e instanceof Error ? e.message : 'Не удалось восстановить сессию.');
      })
      .finally(() => {
        if (active) setRestoring(false);
      });
    return () => {
      active = false;
    };
  }, [sessionAttempt]);

  useEffect(() => {
    if (restoring || sessionError) return;
    const search = viewSearch({
      page,
      profileId: profile?.id ?? null,
      runId: selection?.runId ?? null,
      applicationId,
    });
    window.history.replaceState(null, '', `${window.location.pathname}${search}`);
  }, [restoring, sessionError, page, profile?.id, selection?.runId, applicationId]);

  useEffect(() => {
    const expire = () => {
      clearProtected();
      setError(
        'Сессия завершилась. Войдите снова; сохранённые формы и заявки доступны в кабинете.',
      );
      setLoginOpen(true);
    };
    window.addEventListener('alpha-session-expired', expire);
    const messages =
      typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel('alpha-session');
    channel.current = messages;
    if (messages)
      messages.onmessage = (event) => {
        if (!['login', 'logout'].includes(event.data)) return;
        clearProtected(event.data === 'login');
        setLoginOpen(false);
        setRestoring(true);
        setSessionAttempt((n) => n + 1);
      };
    return () => {
      window.removeEventListener('alpha-session-expired', expire);
      messages?.close();
      channel.current = null;
    };
  }, []);

  // Serialize writes and use the version returned by the previous save. Never overwrite a conflict.
  const saveProfile = (company: Party, current: Answers): Promise<Profile> => {
    const generation = sessionGeneration.current;
    const payload = normalizeAnswers(current);
    const pending = saveQueue.current
      .catch(() => undefined)
      .then(async () => {
        if (generation !== sessionGeneration.current)
          throw new Error('Сессия изменилась. Повторите действие.');
        if (saveConflict.current)
          throw new Error(
            'Форма изменена в другой вкладке. Откройте её заново из «Моих подборов».',
          );
        const previous = profileRef.current;
        if (previous?.partyId === company.id && sameAnswers(previous.answers, payload))
          return previous;
        try {
          const p =
            previous?.partyId === company.id
              ? await api<Profile>(
                  `/selection-profiles/${previous.id}`,
                  { expectedVersion: previous.rowVersion, answers: payload },
                  'PATCH',
                )
              : await api<Profile>('/selection-profiles', {
                  partyId: company.id,
                  answers: payload,
                });
          if (generation !== sessionGeneration.current)
            throw new Error('Сессия изменилась. Повторите действие.');
          profileRef.current = p;
          setProfile(p);
          clearGuestDraft(browserDraftStorage());
          return p;
        } catch (e) {
          if (generation === sessionGeneration.current && e instanceof ApiError && e.status === 409)
            saveConflict.current = true;
          throw e;
        }
      });
    saveQueue.current = pending;
    return pending;
  };

  useEffect(() => {
    const company = writable.find((p) => p.id === partyId);
    if (!authenticated || busy || page !== 'form' || !company || saveConflict.current) return;
    if (
      profileRef.current?.partyId === company.id &&
      sameAnswers(profileRef.current.answers, answers)
    ) {
      setDraftNotice('Черновик сохранён. Можно вернуться к нему из «Моих подборов».');
      return;
    }
    setDraftNotice('Есть несохранённые изменения…');
    let active = true;
    const timer = window.setTimeout(() => {
      setDraftNotice('Сохраняем черновик…');
      void saveProfile(company, answers)
        .then(() => {
          if (active)
            setDraftNotice('Черновик сохранён. Можно вернуться к нему из «Моих подборов».');
        })
        .catch((e) => {
          if (active)
            setDraftNotice(e instanceof Error ? e.message : 'Не удалось сохранить черновик.');
        });
    }, 700);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [authenticated, busy, page, partyId, answers]);

  useEffect(() => {
    if (restoring || authenticated || page !== 'form') return;
    const saved = writeGuestDraft(browserDraftStorage(), answers);
    setDraftNotice(
      saved
        ? 'Черновик сохранён в этой вкладке на 24 часа. После входа он будет доступен в кабинете.'
        : 'Браузер не разрешил сохранить черновик. Не закрывайте страницу до входа.',
    );
  }, [restoring, authenticated, page, answers]);

  useEffect(() => {
    if (!authenticated || page !== 'form' || (profile && sameAnswers(profile.answers, answers)))
      return;
    const protect = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', protect);
    return () => window.removeEventListener('beforeunload', protect);
  }, [authenticated, page, profile, answers]);

  const run = async (action: () => Promise<void>) => {
    if (acting.current || restoring) return;
    acting.current = true;
    setBusy(true);
    setError('');
    try {
      await action();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось выполнить действие.');
    } finally {
      acting.current = false;
      setBusy(false);
    }
  };
  const start = (product?: Product) => {
    if (busy || acting.current) return;
    sessionGeneration.current++;
    const next =
      (!product ? readGuestDraft(browserDraftStorage()) : null) ?? structuredClone(emptyAnswers);
    const company = writable.find((p) => p.id === partyId) ?? writable[0];
    if (company) next.registration.borrowerKind = company.party_kind;
    if (product) {
      clearGuestDraft(browserDraftStorage());
      next.request = {
        ...next.request,
        purpose: product.purposes[0],
        amount: product.minAmount,
        termMonths: Math.min(360, product.minTermMonths),
        usageMode:
          product.policy.facility_kind === 'TERM'
            ? 'ONE_TIME'
            : product.policy.facility_kind === 'OVERDRAFT'
              ? 'ACCOUNT_RESERVE'
              : 'IN_PARTS',
      };
    }
    setDetails(null);
    setAnswers(next);
    profileRef.current = null;
    saveConflict.current = false;
    setDraftNotice('');
    setProfile(null);
    setSelection(null);
    setError('');
    setPage('form');
  };
  const changeParty = (id: string) => {
    sessionGeneration.current++;
    profileRef.current = null;
    saveConflict.current = false;
    setProfile(null);
    setSelection(null);
    setDraftNotice('');
    setPartyId(id);
    const company = writable.find((p) => p.id === id);
    if (company)
      setAnswers((old) => ({
        ...old,
        registration: { ...old.registration, borrowerKind: company.party_kind },
        business: {
          ...old.business,
          taxRegime:
            company.party_kind === 'LLC' && ['PSN', 'NPD'].includes(String(old.business.taxRegime))
              ? 'UNKNOWN'
              : old.business.taxRegime,
        },
      }));
  };
  const submit = async (company: Party, current: Answers) => {
    const next = {
      ...current,
      registration: { ...current.registration, borrowerKind: company.party_kind },
    };
    const p = await saveProfile(company, next);
    setProfile(p);
    setPartyId(company.id);
    setAnswers(next);
    const result = await api<Selection>(`/selection-profiles/${p.id}/automatic-selection`, {});
    setSelection(result);
    setPage('results');
  };
  const loadSaved = async () => {
    const data = await api<{ items: SavedSelection[] }>('/selections');
    setSaved(data.items);
    setPage('saved');
  };
  const navigate = (target: Page) => {
    setError('');
    if (!authenticated && target !== 'catalog') {
      setIntent(target as 'saved' | 'applications');
      setLoginError('');
      setLoginOpen(true);
      return;
    }
    void run(async () => {
      if (page === 'applications') await applicationSave.current?.();
      if (page === 'form' && authenticated) {
        const company = writable.find((p) => p.id === partyId);
        if (company) await saveProfile(company, answers);
      }
      if (target === 'saved') await loadSaved();
      else {
        if (target === 'applications') {
          setApplicationId(null);
          setApplicationRefresh((n) => n + 1);
        }
        setPage(target);
      }
    });
  };
  const showResults = () => {
    if (!authenticated) {
      setIntent('submit');
      setLoginError('');
      setLoginOpen(true);
      return;
    }
    const company = writable.find((p) => p.id === partyId) ?? writable[0];
    if (!company) {
      setError('Нет компании с правом сохранения формы.');
      return;
    }
    void run(() => submit(company, answers));
  };
  const authenticate = async (event: FormEvent) => {
    event.preventDefault();
    if (acting.current || restoring) return;
    acting.current = true;
    setBusy(true);
    setLoginError('');
    let signedIn = false;
    try {
      await api('/auth/session', {
        login: login.trim(),
        password,
      });
      signedIn = true;
      sessionGeneration.current++;
      profileRef.current = null;
      saveConflict.current = false;
      setProfile(null);
      setSelection(null);
      setSaved([]);
      setApplicationId(null);
      const me = await api<{
        user: { display_name: string };
        parties: Party[];
        bankApprover?: boolean;
      }>('/me');
      const dict = await api<Dictionaries>('/forms/preliminary/dictionaries');
      const editable = me.parties.filter((p) => ['OWNER', 'EDITOR'].includes(p.access_role));
      const company = editable.find((p) => p.id === partyId) ?? editable[0];
      setAuthenticated(true);
      setBankApprover(me.bankApprover === true);
      setDisplayName(me.user.display_name);
      setParties(me.parties);
      setDictionary(dict);
      if (company) {
        setPartyId(company.id);
        setAnswers((old) => ({
          ...old,
          registration: { ...old.registration, borrowerKind: company.party_kind },
        }));
      }
      setPassword('');
      setLoginOpen(false);
      setError('');
      setSessionError('');
      channel.current?.postMessage('login');
      if (me.bankApprover) setPage('bank');
      const pending = intent;
      setIntent(null);
      try {
        const guest = readGuestDraft(browserDraftStorage());
        if (guest && company && pending !== 'submit') {
          await saveProfile(company, {
            ...guest,
            registration: { ...guest.registration, borrowerKind: company.party_kind },
          });
        }
        if (pending === 'submit') {
          if (!company) throw new Error('Нет компании с правом сохранения формы.');
          await submit(company, answers);
        } else if (pending === 'saved') await loadSaved();
        else if (pending === 'applications') {
          setApplicationId(null);
          setPage('applications');
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Не удалось продолжить.');
      }
    } catch (e) {
      if (signedIn) {
        await api('/auth/logout', {}).catch(() => undefined);
        setAuthenticated(false);
        setBankApprover(false);
      }
      setLoginError(
        e instanceof ApiError && e.status === 401
          ? 'Неверный логин или пароль. Проверьте данные и попробуйте снова.'
          : e instanceof Error
            ? e.message
            : 'Не удалось войти.',
      );
    } finally {
      acting.current = false;
      setBusy(false);
    }
  };
  const logout = () =>
    void run(async () => {
      if (page === 'applications') await applicationSave.current?.().catch(() => undefined);
      await api('/auth/logout', {});
      channel.current?.postMessage('logout');
      clearProtected();
      setLoginOpen(false);
    });
  const openSaved = (item: SavedSelection) =>
    void run(async () => {
      await saveQueue.current.catch(() => undefined);
      sessionGeneration.current++;
      const p = await api<Profile>(`/selection-profiles/${item.id}`);
      profileRef.current = p;
      saveConflict.current = false;
      setProfile(p);
      setPartyId(p.partyId);
      setAnswers(normalizeAnswers(p.answers));
      if (item.run_id) {
        setSelection(
          await api<Selection>(
            `/selection-profiles/${item.id}/recommendations/${item.run_id}/view`,
          ),
        );
        setPage('results');
      } else setPage('form');
    });
  const choose = (candidate: Candidate) =>
    void run(async () => {
      if (!profile || !selection?.current) throw new Error('Обновите подбор перед оформлением.');
      let p = profile;
      if (
        p.selectedRunId !== selection.runId ||
        p.selectedProductVersionId !== candidate.productVersion
      ) {
        p = await api<Profile>(
          `/selection-profiles/${p.id}/selected-product`,
          {
            expectedVersion: p.rowVersion,
            runId: selection.runId,
            productVersionId: candidate.productVersion,
          },
          'PUT',
        );
        profileRef.current = p;
        saveConflict.current = false;
        setProfile(p);
      }
      const draft = await api<{ id: string }>('/applications', {
        profileId: p.id,
        expectedProfileVersion: p.rowVersion,
        answers: {},
      });
      setApplicationId(draft.id);
      setApplicationRefresh((n) => n + 1);
      setPage('applications');
    });

  const chooseAlternative = (alternative: SelectionAlternative) =>
    void run(async () => {
      if (!profile || !selection?.current) throw new Error('Обновите подбор перед выбором условий.');
      const accepted = await api<{ profile: Profile; selection: Selection }>(
        `/selection-profiles/${profile.id}/recommendations/${selection.runId}/alternatives/${alternative.productVersion}/accept`,
        { expectedVersion: profile.rowVersion },
      );
      profileRef.current = accepted.profile;
      saveConflict.current = false;
      setProfile(accepted.profile);
      setAnswers(normalizeAnswers(accepted.profile.answers));
      setSelection(accepted.selection);
      const draft = await api<{ id: string }>('/applications', {
        profileId: accepted.profile.id,
        expectedProfileVersion: accepted.profile.rowVersion,
        answers: {},
      });
      setApplicationId(draft.id);
      setApplicationRefresh((n) => n + 1);
      setPage('applications');
    });

  return (
    <div className="customer-app">
      <a className="skip-link" href="#content">
        К содержимому
      </a>
      <header className="site-header">
        <div className="header-inner">
          <button
            className="brand"
            onClick={() => navigate('catalog')}
            disabled={busy}
            aria-label="Альфа-Банк — каталог финансирования"
          >
            <span className="brand-symbol">А</span>
            <span>
              Альфа-Банк<small>ДЛЯ БИЗНЕСА</small>
            </span>
          </button>
          <nav aria-label="Основная навигация">
            <button
              aria-current={page === 'catalog' ? 'page' : undefined}
              onClick={() => navigate('catalog')}
              disabled={busy}
            >
              Каталог кредитов
            </button>
            <button
              aria-current={page === 'saved' || page === 'results' ? 'page' : undefined}
              onClick={() => navigate('saved')}
              disabled={busy}
            >
              Мои подборы
            </button>
            <button
              aria-current={page === 'applications' ? 'page' : undefined}
              onClick={() => navigate('applications')}
              disabled={busy}
            >
              Мои заявки
            </button>
            {bankApprover && (
              <button
                aria-current={page === 'bank' ? 'page' : undefined}
                onClick={() => navigate('bank')}
                disabled={busy}
              >
                Кабинет банка
              </button>
            )}
          </nav>
          <div className="header-account">
            {authenticated ? (
              <>
                <span className="account-name">{displayName}</span>
                <Button view="secondary" size={40} disabled={busy} onClick={logout}>
                  Выйти
                </Button>
              </>
            ) : (
              <Button
                view="secondary"
                size={48}
                disabled={busy}
                leftAddons={<Icon name="user" size={18} />}
                onClick={() => {
                  setIntent(null);
                  setLoginError('');
                  setLoginOpen(true);
                }}
              >
                Войти
              </Button>
            )}
          </div>
        </div>
      </header>
      <main id="content" className="site-main">
        {restoring && (
          <div className="loading-panel" role="status">
            Восстанавливаем сессию…
          </div>
        )}
        {sessionError && (
          <Banner tone="error">
            {sessionError}{' '}
            <button
              className="text-action"
              disabled={busy}
              onClick={() => setSessionAttempt((n) => n + 1)}
            >
              Повторить восстановление
            </button>
          </Banner>
        )}
        {page === 'form' && (
          <p role="status" className="fine-print">
            {draftNotice}
          </p>
        )}
        {error && (
          <div className="page-error">
            <Banner tone="error">{error}</Banner>
          </div>
        )}
        {page === 'catalog' && (
          <CatalogPage
            products={products}
            loading={catalogLoading}
            error={catalogError}
            onRetry={() => setCatalogAttempt((n) => n + 1)}
            onStart={start}
            onDetails={setDetails}
          />
        )}
        {page === 'form' && (
          <Wizard
            answers={answers}
            setAnswers={setAnswers}
            parties={writable}
            partyId={partyId}
            onParty={changeParty}
            dictionary={dictionary}
            products={products}
            onBack={() => setPage('catalog')}
            onSubmit={showResults}
            busy={busy}
          />
        )}
        {page === 'results' && selection && (
          <SelectionResults
            selection={selection}
            onDetails={setDetails}
            busy={busy}
            onChoose={choose}
            onAlternative={chooseAlternative}
            onRetry={() =>
              void run(async () => {
                setSelection(
                  await api<Selection>(
                    `/selection-profiles/${selection.profileId}/recommendations/${selection.runId}/retry`,
                    {},
                  ),
                );
              })
            }
            onEdit={() => {
              setPage('form');
              setError('');
            }}
          />
        )}
        {page === 'saved' && (
          <SavedSelections items={saved} onOpen={openSaved} onStart={() => start()} busy={busy} />
        )}
        {page === 'applications' && authenticated && !restoring && (
          <ApplicationsPage
            externalBusy={busy}
            registerSave={(save) => {
              applicationSave.current = save;
            }}
            products={products}
            applicationId={applicationId}
            onOpen={setApplicationId}
            refresh={applicationRefresh}
            onStart={() => start()}
          />
        )}
        {page === 'bank' && authenticated && bankApprover && !restoring && (
          <BankPage products={products} />
        )}
      </main>
      <footer className="site-footer">
        <div className="footer-inner">
          <span>Альфа-Банк · Для бизнеса</span>
          <p>Демонстрационный каталог. Окончательные условия — после рассмотрения заявки.</p>
          <span>© {new Date().getFullYear()}</span>
        </div>
      </footer>
      {details && (
        <ProductDetails product={details} onClose={() => setDetails(null)} onStart={start} />
      )}
      {loginOpen && (
        <Modal
          title="Войти в кабинет"
          onClose={() => {
            if (!busy) {
              setLoginOpen(false);
              setPassword('');
              setIntent(null);
            }
          }}
        >
          <p className="login-caption">
            Сохранённые подборы и заявки будут доступны после входа. Каталог можно смотреть без
            авторизации.
          </p>
          <form className="login-form" onSubmit={authenticate}>
            <Input
              block
              label="Логин"
              value={login}
              onChange={(e) => setLogin(e.target.value)}
              autoComplete="username"
              required
              disabled={busy}
              autoFocus
            />
            <Input
              block
              label="Пароль"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
              disabled={busy}
            />
            {loginError && <Banner tone="error">{loginError}</Banner>}
            <Button block view="accent" size={56} type="submit" loading={busy}>
              Войти в кабинет
            </Button>
          </form>
        </Modal>
      )}
    </div>
  );
}
