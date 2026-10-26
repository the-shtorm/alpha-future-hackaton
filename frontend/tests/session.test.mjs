import { test, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { api, upload, resetCsrf, clearApiSession, ApiError } from '../src/api.ts';
import { readView, viewSearch } from '../src/view.ts';

const originalFetch = globalThis.fetch;
const json = (body, status = 200) => new Response(JSON.stringify(body), { status });
afterEach(() => {
  globalThis.fetch = originalFetch;
  resetCsrf();
  delete globalThis.window;
});

test('GET restoration uses same-origin cookies without exposing an auth token', async () => {
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/me');
    assert.equal(options.credentials, 'same-origin');
    assert.equal(options.cache, 'no-store');
    assert.equal(options.headers.Authorization, undefined);
    return json({ user: { display_name: 'Fixture' } });
  };
  assert.equal((await api('/me')).user.display_name, 'Fixture');
});

test('mutations share one CSRF bootstrap and refresh it after successful login', async () => {
  let bootstraps = 0;
  globalThis.fetch = async (url, options) => {
    if (url === '/api/auth/csrf')
      return json({ headerName: 'X-XSRF-TOKEN', token: `csrf-${++bootstraps}` });
    assert.equal(options.headers['X-XSRF-TOKEN'], `csrf-${bootstraps}`);
    assert.equal(options.credentials, 'same-origin');
    return json({ status: 'ok' });
  };
  await Promise.all([api('/selection-profiles', {}), api('/applications', {})]);
  assert.equal(bootstraps, 1);
  await api('/auth/session', { login: 'fixture', password: 'fixture' });
  await api('/selection-profiles', {});
  assert.equal(bootstraps, 2);
});

test('only a rejected CSRF mutation is retried once, with a refreshed token', async () => {
  let bootstraps = 0,
    mutations = 0;
  globalThis.fetch = async (url, options) => {
    if (url === '/api/auth/csrf')
      return json({ headerName: 'X-XSRF-TOKEN', token: `csrf-${++bootstraps}` });
    assert.equal(options.headers['X-XSRF-TOKEN'], `csrf-${bootstraps}`);
    return ++mutations === 1 ? json({ code: 'CSRF_INVALID' }, 403) : json({ id: 'created' });
  };
  assert.equal((await api('/applications', {})).id, 'created');
  assert.equal(mutations, 2);
  assert.equal(bootstraps, 2);
});

test('persistent CSRF rejection, role denial and network failures never loop/replay', async () => {
  for (const outcome of ['CSRF_INVALID', 'FORBIDDEN', 'network']) {
    resetCsrf();
    let mutations = 0;
    globalThis.fetch = async (url) => {
      if (url === '/api/auth/csrf') return json({ headerName: 'X-XSRF-TOKEN', token: 'fixture' });
      mutations++;
      if (outcome === 'network') throw new TypeError('offline');
      return json({ code: outcome }, 403);
    };
    await assert.rejects(api('/applications', {}), ApiError);
    assert.equal(mutations, outcome === 'CSRF_INVALID' ? 2 : 1);
  }
});

test('multipart upload has cookie and CSRF but lets the browser choose its boundary', async () => {
  const form = new FormData();
  form.set('file', new Blob(['fixture']), 'fixture.pdf');
  globalThis.fetch = async (url, options) => {
    if (url === '/api/auth/csrf') return json({ headerName: 'X-XSRF-TOKEN', token: 'fixture' });
    assert.equal(options.credentials, 'same-origin');
    assert.equal(options.body, form);
    assert.equal(options.headers['Content-Type'], undefined);
    assert.equal(options.headers['X-XSRF-TOKEN'], 'fixture');
    return json({});
  };
  await upload('/applications/fixture/documents', form);
});

test('expired private requests notify the app; initial anonymous /me and bad passwords do not', async () => {
  globalThis.window = new EventTarget();
  let events = 0;
  window.addEventListener('alpha-session-expired', () => events++);
  globalThis.fetch = async (url) =>
    url === '/api/auth/csrf'
      ? json({ headerName: 'X-XSRF-TOKEN', token: 'fixture' })
      : json({}, 401);
  await assert.rejects(api('/me'));
  await assert.rejects(api('/auth/session', {}));
  assert.equal(events, 0);
  await assert.rejects(api('/applications'));
  assert.equal(events, 1);
});

test('CSRF headers cannot be sent to arbitrary origins through the API helper', async () => {
  globalThis.fetch = async () => assert.fail('fetch must not run');
  for (const path of ['https://example.com', '//example.com', '/../../elsewhere', '/\\example.com'])
    await assert.rejects(api(path, {}));
});

test('reload URL preserves only validated resource identifiers and the current screen', () => {
  const profileId = '12345678-1234-1234-1234-123456789abc';
  const runId = '87654321-1234-1234-1234-123456789abc';
  const view = { page: 'results', profileId, runId, applicationId: null };
  assert.deepEqual(readView(viewSearch(view)), view);
  assert.equal(viewSearch({ ...view, page: 'catalog' }), '');
  assert.deepEqual(readView('?page=evil&profile=../me&run=token&accessToken=secret'), {
    page: 'catalog',
    profileId: null,
    runId: null,
    applicationId: null,
  });
  const application = { ...view, page: 'applications', applicationId: profileId };
  assert.equal(viewSearch(application), `?page=applications&application=${profileId}`);
});

test('responses started under an old session cannot repopulate a cleared cabinet', async () => {
  let finish;
  globalThis.fetch = () =>
    new Promise((resolve) => {
      finish = resolve;
    });
  const pending = api('/applications');
  clearApiSession();
  finish(json({ content: [{ id: 'private-old-session' }] }));
  await assert.rejects(pending, (error) => error.code === 'SESSION_CHANGED');
});

test('anonymous /me restoration or login changes do not invalidate the public catalog', async () => {
  let finish;
  globalThis.fetch = () =>
    new Promise((resolve) => {
      finish = resolve;
    });
  const pending = api('/products?page=0&size=50');
  clearApiSession();
  finish(json({ content: [{ id: 'public-product' }] }));
  assert.equal((await pending).content[0].id, 'public-product');
});
