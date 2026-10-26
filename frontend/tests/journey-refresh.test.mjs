import { test } from 'node:test';
import assert from 'node:assert/strict';
import { shouldRefreshApplication, canApplyJourney } from '../src/journeyRefresh.ts';

const journey = (id, rowVersion) => ({ application: { id, rowVersion } });
test('waiting and confirmation stages refresh, editable drafts and terminal states do not', () => {
  for (const status of [
    'SUBMITTED',
    'UNDER_REVIEW',
    'APPROVED',
    'COUNTEROFFERED',
    'OFFER_ACCEPTED',
    'SIGNED',
  ])
    assert.equal(shouldRefreshApplication(status), true, status);
  for (const status of ['DRAFT', 'NEEDS_INFO', 'DECLINED', 'DISBURSED', 'CANCELLED', 'EXPIRED'])
    assert.equal(shouldRefreshApplication(status), false, status);
});
test('late snapshot cannot regress the application or cross into a different open application', () => {
  assert.equal(canApplyJourney(journey('a', 8), journey('a', 7), 'a'), false);
  assert.equal(canApplyJourney(journey('a', 8), journey('b', 9), 'a'), false);
  assert.equal(canApplyJourney(journey('b', 1), journey('a', 9), 'a'), false);
  assert.equal(canApplyJourney(null, journey('a', 9), 'a'), false);
});
test('newer status and equal-version document reviews can both refresh the screen', () => {
  assert.equal(canApplyJourney(journey('a', 8), journey('a', 9), 'a'), true);
  assert.equal(canApplyJourney(journey('a', 8), journey('a', 8), 'a'), true);
});
