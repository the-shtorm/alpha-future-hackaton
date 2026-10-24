import { test } from 'node:test';
import assert from 'node:assert/strict';
import { emptyAnswers, normalizeAnswers, exampleAnswers } from '../src/form.ts';

test('export serialization preserves declared false, zero and explicit unknown, leaves blank values null', () => {
  const input = structuredClone(emptyAnswers);
  input.business.mspRegistry = false;
  input.business.bankAccountMonths = 0;
  input.request.description = '   ';
  input.security.guarantorReady = 'DISCUSS';
  const serialized = JSON.parse(JSON.stringify(normalizeAnswers(input)));
  assert.equal(serialized.business.mspRegistry, false);
  assert.equal(serialized.business.bankAccountMonths, 0);
  assert.equal(serialized.business.marketplaceMonths, null);
  assert.equal(serialized.security.collateralReady, 'UNKNOWN');
  assert.equal(serialized.security.guarantorReady, 'DISCUSS');
  assert.equal(serialized.request.description, null);
  assert.equal(serialized.financial.revenue, null);
});

test('switching IP to LLC does not submit an entrepreneurs age or mutate the visible form', () => {
  const input = structuredClone(emptyAnswers);
  input.business.ipAgeYears = 42;
  const output = normalizeAnswers(input);
  assert.equal('ipAgeYears' in output.business, false);
  assert.equal(input.business.ipAgeYears, 42);
  input.registration.borrowerKind = 'IP';
  assert.equal(normalizeAnswers(input).business.ipAgeYears, 42);
});

test('synthetic example covers twelve complete past calendar months and uses new codes', () => {
  const input = exampleAnswers();
  const from = new Date(input.financial.periodFrom);
  const to = new Date(input.financial.periodTo);
  assert.equal(from.getUTCDate(), 1);
  assert.equal(new Date(to.getTime() + 86400000).getUTCDate(), 1);
  assert.equal(
    (to.getUTCFullYear() - from.getUTCFullYear()) * 12 + to.getUTCMonth() - from.getUTCMonth() + 1,
    12,
  );
  assert.ok(to < new Date());
  assert.equal(input.request.usageMode, 'IN_PARTS');
  assert.equal(input.security.guarantorReady, 'DISCUSS');
  assert.equal(input.request.amount, '1000000.00');
});
