import { test } from 'node:test';
import assert from 'node:assert/strict';
import { emptyAnswers, normalizeAnswers, exampleAnswers } from '../src/form.ts';
import { rate, matchesAmount } from '../src/presentation.ts';

test('preliminary payload has fifteen fields and preserves explicit false and unknowns', () => {
  const input = structuredClone(emptyAnswers);
  input.business.mspRegistry = false;
  input.request.description = '   ';
  input.security.guarantorReady = 'DISCUSS';
  const serialized = JSON.parse(JSON.stringify(normalizeAnswers(input)));
  assert.equal(Object.values(serialized).flatMap((section) => Object.keys(section)).length, 15);
  assert.equal(serialized.business.mspRegistry, false);
  assert.equal(serialized.business.sector, null);
  assert.equal(serialized.security.collateralReady, 'UNKNOWN');
  assert.equal(serialized.security.guarantorReady, 'DISCUSS');
  assert.equal(serialized.request.description, null);
  assert.equal(serialized.financial.revenue, null);
});

test('obsolete fields do not enter the new API payload, including for IP, without mutating input', () => {
  for (const kind of ['IP', 'LLC']) {
    const input = structuredClone(emptyAnswers);
    input.registration = { borrowerKind: kind, registeredOn: '2020-01-01', country: 'RU' };
    input.business = {
      ...input.business,
      region: '77',
      ipAgeYears: 42,
      marketplaceMonths: 12,
      bankAccountMonths: 12,
    };
    const output = normalizeAnswers(input);
    assert.deepEqual(Object.keys(output.registration), ['borrowerKind']);
    for (const key of ['region', 'ipAgeYears', 'marketplaceMonths', 'bankAccountMonths'])
      assert.equal(key in output.business, false);
    assert.equal(input.business.ipAgeYears, 42);
  }
});

test('money is serialized to two decimal places without losing precision or replacing unknown with zero', () => {
  const input = structuredClone(emptyAnswers);
  input.request.amount = ' 1 000 000,5 ₽ ';
  input.financial.revenue = '99999999999999999.99';
  input.financial.monthlyDebtPayment = '0';
  input.financial.overdue = 0;
  const output = normalizeAnswers(input);
  assert.equal(output.request.amount, '1000000.50');
  assert.equal(output.financial.revenue, '99999999999999999.99');
  assert.equal(output.financial.monthlyDebtPayment, '0.00');
  assert.equal(output.financial.overdue, 0);
  assert.equal(input.request.amount, ' 1 000 000,5 ₽ ');
  input.request.amount = '';
  assert.equal(normalizeAnswers(input).request.amount, null);
});

test('invalid precision stays invalid instead of being silently rounded', () => {
  const input = structuredClone(emptyAnswers);
  input.request.amount = '100.001';
  assert.equal(normalizeAnswers(input).request.amount, '100.001');
});

test('synthetic example covers twelve complete past months and a compatible one-time usage', () => {
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
  assert.equal(input.request.usageMode, 'ONE_TIME');
  assert.equal(input.security.guarantorReady, 'DISCUSS');
  assert.equal(input.request.amount, '1000000.00');
  assert.equal(Object.values(input).flatMap((section) => Object.keys(section)).length, 15);
});

test('product rate formatting preserves integer trailing zeros', () => {
  assert.equal(rate('20'), '20%');
  assert.equal(rate('0'), '0%');
  assert.equal(rate('20.00000'), '20%');
  assert.equal(rate('20.50000'), '20.5%');
  assert.equal(rate(null), 'По условиям продукта');
});

test('catalog amount filtering includes exact boundaries without floating-point loss', () => {
  const product = { minAmount: '9007199254740992.01', maxAmount: '9007199254740992.02' };
  assert.equal(matchesAmount(product, '9007199254740992.00'), false);
  assert.equal(matchesAmount(product, '9 007 199 254 740 992,01'), true);
  assert.equal(matchesAmount(product, '9007199254740992.02'), true);
  assert.equal(matchesAmount(product, '9007199254740992.03'), false);
  assert.equal(matchesAmount(product, 'invalid'), false);
  assert.equal(matchesAmount(product, ''), true);
});
