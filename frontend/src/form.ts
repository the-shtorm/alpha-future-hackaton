import type { Answers } from './types';

export const emptyAnswers: Answers = {
  registration: { borrowerKind: 'LLC', registeredOn: '', country: 'RU' },
  business: {
    sector: 'UNKNOWN',
    actualStartedOn: '',
    taxRegime: 'UNKNOWN',
    mspRegistry: null,
    region: '',
    ipAgeYears: null,
    marketplaceMonths: null,
    bankAccountMonths: null,
  },
  request: {
    purpose: 'WORKING_CAPITAL',
    amount: '',
    termMonths: 12,
    usageMode: 'UNKNOWN',
    description: null,
  },
  financial: { revenue: '', periodFrom: '', periodTo: '' },
  security: { collateralReady: 'UNKNOWN', guarantorReady: 'UNKNOWN' },
};

export function normalizeAnswers(form: Answers): Answers {
  return Object.fromEntries(
    Object.entries(form).map(([section, fields]) => [
      section,
      Object.fromEntries(
        Object.entries(fields)
          .filter(
            ([key]) =>
              !(
                section === 'business' &&
                key === 'ipAgeYears' &&
                form.registration.borrowerKind !== 'IP'
              ),
          )
          .map(([key, value]) => [
            key,
            typeof value === 'string'
              ? (['amount','revenue','monthlyDebtPayment','collateralValue','ownContributionPct'].includes(key)
                  ? value.replace(/[\s\u00a0₽]/g,'').replace(',','.')
                  : value.trim().replace(/\s+/g,' ')) || null
              : value,
          ]),
      ),
    ]),
  );
}

export function exampleAnswers(): Answers {
  // Synthetic values only, never presented as the current user's business data.
  const end = new Date();
  end.setUTCDate(0);
  const start = new Date(Date.UTC(end.getUTCFullYear(), end.getUTCMonth() - 11, 1));
  return {
    ...structuredClone(emptyAnswers),
    registration: { borrowerKind: 'LLC', registeredOn: '2020-01-01', country: 'RU' },
    business: {
      sector: 'TRADE',
      actualStartedOn: '2020-02-01',
      taxRegime: 'USN',
      mspRegistry: true,
      region: '77',
      marketplaceMonths: null,
      bankAccountMonths: 12,
    },
    request: {
      purpose: 'WORKING_CAPITAL',
      amount: '1000000.00',
      termMonths: 12,
      usageMode: 'IN_PARTS',
      description: 'Закупаем товар небольшими партиями перед сезоном',
    },
    financial: {
      revenue: '24000000.00',
      periodFrom: start.toISOString().slice(0, 10),
      periodTo: end.toISOString().slice(0, 10),
    },
    security: { collateralReady: 'NO', guarantorReady: 'DISCUSS' },
  };
}
