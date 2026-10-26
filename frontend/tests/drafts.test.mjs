import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readGuestDraft, writeGuestDraft, clearGuestDraft, DraftWriter } from '../src/drafts.ts';
import { emptyAnswers } from '../src/form.ts';

function storage() {
  const data = new Map();
  return {
    data,
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => data.set(key, value),
    removeItem: (key) => data.delete(key),
  };
}
const now = 1000000000;
test('guest form restores exact inputs, zero, false and unknown values in this tab', () => {
  const store = storage();
  const answers = structuredClone(emptyAnswers);
  answers.request.description = 'Synthetic draft';
  answers.request.amount = ' 1 000 000,50 ';
  answers.business.mspRegistry = false;
  answers.financial.revenue = 0;
  assert.ok(writeGuestDraft(store, answers, now));
  assert.deepEqual(readGuestDraft(store, now + 1000), answers);
  assert.equal(readGuestDraft(storage(), now + 1000), null);
});

test('guest persistence never copies credentials, resource IDs or final application fields', () => {
  const store = storage();
  const answers = {
    ...structuredClone(emptyAnswers),
    auth: { password: 'must-not-copy', accessToken: 'must-not-copy' },
    id: 'private-id',
  };
  answers.financial.monthlyDebtPayment = 'must-not-copy';
  writeGuestDraft(store, answers, now);
  assert.ok(![...store.data.values()][0].includes('must-not-copy'));
  assert.equal(readGuestDraft(store, now).financial.monthlyDebtPayment, undefined);
  assert.equal(readGuestDraft(store, now).auth, undefined);
  clearGuestDraft(store);
  assert.equal(store.data.size, 0);
});

test('expired, future, corrupt, oversized and incompatible stored drafts are removed', () => {
  for (const value of [
    '{bad',
    'x'.repeat(16001),
    JSON.stringify({ version: 2, savedAt: now, answers: {} }),
    JSON.stringify({ version: 1, savedAt: now + 100, answers: {} }),
    JSON.stringify({ version: 1, savedAt: now - 86400001, answers: {} }),
  ]) {
    const store = storage();
    writeGuestDraft(store, emptyAnswers, now);
    store.setItem([...store.data.keys()][0], value);
    assert.equal(readGuestDraft(store, now), null);
    assert.equal(store.data.size, 0);
  }
});

test('malicious stored values cannot inject objects or excessively long fields into the form', () => {
  const store = storage();
  writeGuestDraft(
    store,
    {
      ...structuredClone(emptyAnswers),
      request: { amount: { nested: 'bad' }, description: 'x'.repeat(501) },
    },
    now,
  );
  const restored = readGuestDraft(store, now);
  assert.equal(restored.request.amount, '');
  assert.equal(restored.request.description, null);
});

test('disabled storage does not crash the application or claim a draft was saved', () => {
  const denied = {
    getItem() {
      throw new Error('denied');
    },
    setItem() {
      throw new Error('denied');
    },
    removeItem() {
      throw new Error('denied');
    },
  };
  assert.equal(readGuestDraft(denied), null);
  assert.equal(writeGuestDraft(denied, emptyAnswers), false);
  assert.equal(writeGuestDraft(null, emptyAnswers), false);
  assert.equal(readGuestDraft(null), null);
  clearGuestDraft(denied);
});

test('autosave and explicit save serialize and take rowVersion from the previous response', async () => {
  const versions = [],
    updates = [];
  const writer = new DraftWriter({ rowVersion: 3, answers: {} }, async (current, answers) => {
    versions.push(current.rowVersion);
    updates.push(answers);
    await new Promise((resolve) => setImmediate(resolve));
    return { rowVersion: current.rowVersion + 1, answers };
  });
  const first = writer.save({ financial: { monthlyDebtPayment: '10' } });
  const second = writer.save({ financial: { monthlyDebtPayment: '20' } });
  assert.equal((await first).answers.financial.monthlyDebtPayment, '10.00');
  assert.equal((await second).answers.financial.monthlyDebtPayment, '20.00');
  assert.deepEqual(versions, [3, 4]);
  assert.equal(writer.current.rowVersion, 5);
  assert.equal(updates.length, 2);
});

test('queued save snapshots are not changed by later edits, and the latest save wins', async () => {
  const writer = new DraftWriter({ rowVersion: 0, answers: {} }, async (current, answers) => ({
    rowVersion: current.rowVersion + 1,
    answers,
  }));
  const answers = { request: { description: 'First' } };
  const first = writer.save(answers);
  answers.request.description = 'Second';
  const second = writer.save(answers);
  assert.equal((await first).answers.request.description, 'First');
  assert.equal((await second).answers.request.description, 'Second');
});

test('equivalent or repeated answers do not issue redundant PATCH requests', async () => {
  let count = 0;
  const writer = new DraftWriter(
    { rowVersion: 0, answers: { request: { amount: '10.00' } } },
    async (current, answers) => {
      count++;
      return { rowVersion: current.rowVersion + 1, answers };
    },
  );
  await writer.save({ request: { amount: '10' } });
  await Promise.all([
    writer.save({ request: { amount: '20' } }),
    writer.save({ request: { amount: '20.00' } }),
  ]);
  assert.equal(count, 1);
});

test('version conflicts stop further writes instead of overwriting another tab', async () => {
  let calls = 0;
  const writer = new DraftWriter({ rowVersion: 0, answers: {} }, async () => {
    calls++;
    throw Object.assign(new Error('conflict'), { status: 409 });
  });
  await assert.rejects(writer.save({ request: { amount: '10' } }));
  await assert.rejects(writer.save({ request: { amount: '20' } }));
  assert.ok(writer.blocked);
  assert.equal(calls, 1);
});

test('unknown write outcome still respects optimistic locking on explicit retry', async () => {
  let version = 0,
    calls = 0;
  const writer = new DraftWriter({ rowVersion: 0, answers: {} }, async (current) => {
    calls++;
    if (current.rowVersion !== version) throw Object.assign(new Error('conflict'), { status: 409 });
    version++;
    throw Object.assign(new Error('connection lost after commit'), { status: 0 });
  });
  await assert.rejects(writer.save({ request: { amount: '10' } }));
  await assert.rejects(writer.save({ request: { amount: '20' } }));
  assert.equal(version, 1);
  assert.equal(calls, 2);
  assert.ok(writer.blocked);
});

test('closing a form rejects queued saves and does not repopulate state from a late response', async () => {
  let finish,
    calls = 0;
  const writer = new DraftWriter({ rowVersion: 0, answers: {} }, () => {
    calls++;
    return new Promise((resolve) => {
      finish = resolve;
    });
  });
  const first = writer.save({ request: { amount: '10' } });
  const second = writer.save({ request: { amount: '20' } });
  const settled = Promise.allSettled([first, second]);
  await new Promise((resolve) => setImmediate(resolve));
  writer.dispose();
  finish({ rowVersion: 1, answers: { request: { amount: '10' } } });
  assert.ok((await settled).every((item) => item.status === 'rejected'));
  assert.equal(calls, 1);
  assert.equal(writer.current.rowVersion, 0);
});
