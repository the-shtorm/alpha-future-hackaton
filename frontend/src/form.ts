import type { Answers } from './types';

export const emptyAnswers: Answers = {
  registration: { borrowerKind: 'LLC' },
  business: {
    sector: null,
    actualStartedOn: '',
    taxRegime: 'UNKNOWN',
    mspRegistry: null,
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

const removedFields = new Set([
  'registration.registeredOn',
  'registration.country',
  'business.region',
  'business.ipAgeYears',
  'business.marketplaceMonths',
  'business.bankAccountMonths',
]);
const decimalFields = new Set([
  'request.amount',
  'financial.revenue',
  'financial.monthlyDebtPayment',
  'security.collateralValue',
  'project.ownContributionPct',
]);

/** Prepares decimal strings without converting money to floating-point numbers. */
export function normalizeAnswers(form: Answers): Answers {
  return Object.fromEntries(
    Object.entries(form).map(([section, fields]) => [
      section,
      Object.fromEntries(
        Object.entries(fields)
          .filter(([key]) => !removedFields.has(`${section}.${key}`))
          .map(([key, value]) => {
            if (typeof value !== 'string') return [key, value];
            const path = `${section}.${key}`;
            let text = decimalFields.has(path)
              ? value.replace(/[\s\u00a0₽]/g, '').replace(',', '.')
              : value.trim().replace(/\s+/g, ' ');
            if (decimalFields.has(path) && /^(?:0|[1-9]\d{0,16})(?:\.\d{1,2})?$/.test(text)) {
              const [whole, fraction = ''] = text.split('.');
              text = `${whole}.${fraction.padEnd(2, '0')}`;
            }
            return [key, text || null];
          }),
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
    business: {
      sector: 'TRADE',
      actualStartedOn: '2020-02-01',
      taxRegime: 'USN',
      mspRegistry: true,
    },
    request: {
      purpose: 'WORKING_CAPITAL',
      amount: '1000000.00',
      termMonths: 12,
      usageMode: 'ONE_TIME',
      description: 'Закупаем товар перед сезоном',
    },
    financial: {
      revenue: '24000000.00',
      periodFrom: start.toISOString().slice(0, 10),
      periodTo: end.toISOString().slice(0, 10),
    },
    security: { collateralReady: 'NO', guarantorReady: 'DISCUSS' },
  };
}
