import type { Journey } from './types';

const waiting = new Set([
  'SUBMITTED',
  'UNDER_REVIEW',
  'VALIDATING',
  'ENRICHING',
  'SCORING',
  'COMPLIANCE_REVIEW',
  'LEGAL_REVIEW',
  'APPROVED',
  'APPROVED_CONDITIONAL',
  'COUNTEROFFERED',
  'OFFER_ACCEPTED',
  'SIGNED',
  'CONTRACT_SIGNED',
  'READY_FOR_DISBURSEMENT',
]);

export function shouldRefreshApplication(status: string): boolean {
  return waiting.has(status);
}

export function canApplyJourney(current: Journey | null, next: Journey, id: string): boolean {
  return (
    current?.application.id === id &&
    next.application.id === id &&
    next.application.rowVersion >= current.application.rowVersion
  );
}
