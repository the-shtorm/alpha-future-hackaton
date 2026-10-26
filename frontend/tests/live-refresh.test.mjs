import { test } from 'node:test';
import assert from 'node:assert/strict';
import { startLiveRefresh } from '../src/liveRefresh.ts';

const settle = async () => {
  await Promise.resolve();
  await Promise.resolve();
};

function browser(visible = true) {
  let now = 0;
  let sequence = 0;
  const timers = new Map();
  const focus = new Set();
  const visibility = new Set();
  const listen = (listeners) => (callback) => {
    listeners.add(callback);
    return () => listeners.delete(callback);
  };
  return {
    environment: {
      isVisible: () => visible,
      schedule: (callback, delay) => {
        const id = ++sequence;
        timers.set(id, { at: now + delay, callback });
        return id;
      },
      cancel: (id) => timers.delete(id),
      onFocus: listen(focus),
      onVisibilityChange: listen(visibility),
    },
    pending: () => timers.size,
    listeners: () => focus.size + visibility.size,
    focus: () => focus.forEach((callback) => callback()),
    visibility: (next) => {
      visible = next;
      visibility.forEach((callback) => callback());
    },
    async advance(ms) {
      const end = now + ms;
      while (true) {
        const next = [...timers].sort((a, b) => a[1].at - b[1].at)[0];
        if (!next || next[1].at > end) break;
        const [id, timer] = next;
        timers.delete(id);
        now = timer.at;
        timer.callback();
        await settle();
      }
      now = end;
      await settle();
    },
  };
}

test('initial load is not repeated; visible pages refresh every five seconds', async () => {
  const tab = browser();
  let calls = 0;
  const stop = startLiveRefresh(
    async () => {
      calls++;
    },
    { environment: tab.environment },
  );
  assert.equal(calls, 0);
  await tab.advance(4999);
  assert.equal(calls, 0);
  await tab.advance(1);
  assert.equal(calls, 1);
  assert.equal(tab.pending(), 1);
  await tab.advance(5000);
  assert.equal(calls, 2);
  stop();
});

test('hidden pages do not poll; becoming visible refreshes immediately and resumes polling', async () => {
  const tab = browser(false);
  let calls = 0;
  const stop = startLiveRefresh(
    async () => {
      calls++;
    },
    { environment: tab.environment },
  );
  assert.equal(tab.pending(), 0);
  await tab.advance(20000);
  assert.equal(calls, 0);
  tab.visibility(true);
  await settle();
  assert.equal(calls, 1);
  await tab.advance(5000);
  assert.equal(calls, 2);
  tab.visibility(false);
  assert.equal(tab.pending(), 0);
  await tab.advance(20000);
  tab.focus();
  await settle();
  assert.equal(calls, 2);
  stop();
});

test('focus refreshes immediately and resets the next polling deadline', async () => {
  const tab = browser();
  let calls = 0;
  const stop = startLiveRefresh(
    async () => {
      calls++;
    },
    { environment: tab.environment },
  );
  await tab.advance(4000);
  tab.focus();
  await settle();
  assert.equal(calls, 1);
  await tab.advance(1000);
  assert.equal(calls, 1);
  await tab.advance(4000);
  assert.equal(calls, 2);
  stop();
});

test('slow requests never overlap or queue duplicate focus/visibility requests', async () => {
  const tab = browser();
  let calls = 0;
  let complete;
  const stop = startLiveRefresh(
    () => {
      calls++;
      return new Promise((resolve) => {
        complete = resolve;
      });
    },
    { environment: tab.environment },
  );
  await tab.advance(5000);
  assert.equal(calls, 1);
  assert.equal(tab.pending(), 0);
  await tab.advance(50000);
  tab.focus();
  tab.visibility(true);
  tab.focus();
  assert.equal(calls, 1);
  complete();
  await settle();
  assert.equal(tab.pending(), 1);
  await tab.advance(4999);
  assert.equal(calls, 1);
  await tab.advance(1);
  assert.equal(calls, 2);
  stop();
  complete();
  await settle();
});

test('cleanup removes timers/listeners and prevents focus or visibility work', async () => {
  const tab = browser();
  let calls = 0;
  const stop = startLiveRefresh(
    async () => {
      calls++;
    },
    { environment: tab.environment },
  );
  assert.equal(tab.listeners(), 2);
  stop();
  stop();
  assert.equal(tab.listeners(), 0);
  assert.equal(tab.pending(), 0);
  tab.focus();
  tab.visibility(true);
  await tab.advance(10000);
  assert.equal(calls, 0);
});

test('cleanup during a request prevents its completion from scheduling another poll', async () => {
  const tab = browser();
  let complete;
  let calls = 0;
  const stop = startLiveRefresh(
    () => {
      calls++;
      return new Promise((resolve) => {
        complete = resolve;
      });
    },
    { environment: tab.environment },
  );
  tab.focus();
  assert.equal(calls, 1);
  stop();
  complete();
  await settle();
  await tab.advance(20000);
  assert.equal(calls, 1);
  assert.equal(tab.pending(), 0);
  assert.equal(tab.listeners(), 0);
});

test('a rejected refresh is contained and the next poll can succeed', async () => {
  const tab = browser();
  let calls = 0;
  const stop = startLiveRefresh(
    async () => {
      calls++;
      if (calls === 1) throw new Error('Temporary network failure');
    },
    { environment: tab.environment, intervalMs: 100 },
  );
  await tab.advance(100);
  assert.equal(calls, 1);
  assert.equal(tab.pending(), 1);
  await tab.advance(100);
  assert.equal(calls, 2);
  stop();
});
