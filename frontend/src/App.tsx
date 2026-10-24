import { useEffect, useState, type FormEvent } from 'react';
import { api, ApiError } from './api';
import { emptyAnswers, normalizeAnswers } from './form';
import { dictionaries } from './presentation';
import { CatalogPage, ProductDetails } from './components/Catalog';
import { SelectionResults, SavedSelections } from './components/Selections';
import { Wizard } from './components/Wizard';
import { ApplicationsPage } from './components/Applications';
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
} from './types';

type Page = 'catalog' | 'form' | 'results' | 'saved' | 'applications';
type Intent = 'submit' | 'saved' | 'applications' | null;

export function App() {
  const [page, setPage] = useState<Page>('catalog');
  const [products, setProducts] = useState<Product[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState('');
  const [catalogAttempt, setCatalogAttempt] = useState(0);
  const [details, setDetails] = useState<Product | null>(null);
  const [answers, setAnswers] = useState<Answers>(() => structuredClone(emptyAnswers));
  const [dictionary, setDictionary] = useState<Dictionaries>(dictionaries);
  const [token, setToken] = useState('');
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
  const [busy, setBusy] = useState(false);
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

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError('');
    try {
      await action();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось выполнить действие.');
    } finally {
      setBusy(false);
    }
  };
  const start = (product?: Product) => {
    const next = structuredClone(emptyAnswers);
    const company = writable.find((p) => p.id === partyId) ?? writable[0];
    if (company) next.registration.borrowerKind = company.party_kind;
    if (product) {
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
    setProfile(null);
    setSelection(null);
    setError('');
    setPage('form');
  };
  const changeParty = (id: string) => {
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
  const submit = async (auth: string, company: Party, current: Answers) => {
    const next = {
      ...current,
      registration: { ...current.registration, borrowerKind: company.party_kind },
    };
    const p = await api<Profile>('/selection-profiles', auth, {
      partyId: company.id,
      answers: normalizeAnswers(next),
    });
    setProfile(p);
    setPartyId(company.id);
    setAnswers(next);
    const result = await api<Selection>(
      `/selection-profiles/${p.id}/automatic-selection`,
      auth,
      {},
    );
    setSelection(result);
    setPage('results');
  };
  const loadSaved = async (auth: string) => {
    const data = await api<{ items: SavedSelection[] }>('/selections', auth);
    setSaved(data.items);
    setPage('saved');
  };
  const navigate = (target: Page) => {
    setError('');
    if (target === 'catalog') {
      setPage('catalog');
      return;
    }
    if (!token) {
      setIntent(target as 'saved' | 'applications');
      setLoginError('');
      setLoginOpen(true);
      return;
    }
    if (target === 'saved') void run(() => loadSaved(token));
    else {
      setApplicationId(null);
      setPage(target);
      setApplicationRefresh((n) => n + 1);
    }
  };
  const showResults = () => {
    if (!token) {
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
    void run(() => submit(token, company, answers));
  };
  const authenticate = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setLoginError('');
    let auth = '';
    try {
      const session = await api<{ accessToken: string }>('/auth/login', '', {
        login: login.trim(),
        password,
      });
      auth = session.accessToken;
      const me = await api<{ user: { display_name: string }; parties: Party[] }>('/me', auth);
      const dict = await api<Dictionaries>('/forms/preliminary/dictionaries', auth);
      const editable = me.parties.filter((p) => ['OWNER', 'EDITOR'].includes(p.access_role));
      const company = editable.find((p) => p.id === partyId) ?? editable[0];
      setToken(auth);
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
      const pending = intent;
      setIntent(null);
      try {
        if (pending === 'submit') {
          if (!company) throw new Error('Нет компании с правом сохранения формы.');
          await submit(auth, company, answers);
        } else if (pending === 'saved') await loadSaved(auth);
        else if (pending === 'applications') {
          setApplicationId(null);
          setPage('applications');
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Не удалось продолжить.');
      }
    } catch (e) {
      if (auth) await api('/auth/logout', auth, {}).catch(() => undefined);
      setLoginError(
        e instanceof ApiError && e.status === 401
          ? 'Неверный логин или пароль. Проверьте данные и попробуйте снова.'
          : e instanceof Error
            ? e.message
            : 'Не удалось войти.',
      );
    } finally {
      setBusy(false);
    }
  };
  const logout = () =>
    void run(async () => {
      await api('/auth/logout', token, {});
      setToken('');
      setParties([]);
      setPartyId('');
      setDisplayName('');
      setSaved([]);
      setAnswers(structuredClone(emptyAnswers));
      setProfile(null);
      setSelection(null);
      setApplicationId(null);
      setPage('catalog');
    });
  const openSaved = (item: SavedSelection) =>
    void run(async () => {
      const p = await api<Profile>(`/selection-profiles/${item.id}`, token);
      setProfile(p);
      setPartyId(p.partyId);
      setAnswers(normalizeAnswers(p.answers));
      if (item.run_id) {
        setSelection(
          await api<Selection>(
            `/selection-profiles/${item.id}/recommendations/${item.run_id}/view`,
            token,
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
          token,
          {
            expectedVersion: p.rowVersion,
            runId: selection.runId,
            productVersionId: candidate.productVersion,
          },
          'PUT',
        );
        setProfile(p);
      }
      const draft = await api<{ id: string }>('/applications', token, {
        profileId: p.id,
        expectedProfileVersion: p.rowVersion,
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
          </nav>
          <div className="header-account">
            {token ? (
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
                onClick={() => {
                  setIntent(null);
                  setLoginError('');
                  setLoginOpen(true);
                }}
              >
                <Icon name="user" size={18} />
                Войти
              </Button>
            )}
          </div>
        </div>
      </header>
      <main id="content" className="site-main">
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
            onRetry={() =>
              void run(async () => {
                setSelection(
                  await api<Selection>(
                    `/selection-profiles/${selection.profileId}/recommendations/${selection.runId}/retry`,
                    token,
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
        {page === 'applications' && token && (
          <ApplicationsPage
            token={token}
            products={products}
            applicationId={applicationId}
            onOpen={setApplicationId}
            refresh={applicationRefresh}
            onStart={() => start()}
          />
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
