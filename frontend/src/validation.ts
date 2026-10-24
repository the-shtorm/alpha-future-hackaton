import type { Answers, Product } from './types';
import { money, parseMoney } from './presentation.ts';

export type FieldErrors = Record<string, string>;
/** Pure input/catalog checks, separate from credit scoring or an approval decision. */
export function validatePreliminary(
  answers: Answers,
  products: Product[],
  stage: number,
  today = new Date().toISOString().slice(0, 10),
): FieldErrors {
  const errors: FieldErrors = {};
  const value = (path: string) => {
    const [s, k] = path.split('.');
    return answers[s]?.[k];
  };
  const filled = (path: string) =>
    value(path) !== null && value(path) !== undefined && String(value(path)).trim() !== '';
  const validDate = (raw: string) =>
    /^\d{4}-\d{2}-\d{2}$/.test(raw) &&
    !Number.isNaN(Date.parse(raw)) &&
    new Date(raw).toISOString().slice(0, 10) === raw;
  const checkDate = (path: string) => {
    if (filled(path) && (!validDate(String(value(path))) || String(value(path)) > today))
      errors[path] = 'Укажите существующую дату не позже сегодняшнего дня';
  };
  if (stage === 0 || stage === 2) checkDate('business.actualStartedOn');
  if (stage === 1 || stage === 2) {
    const amount = parseMoney(String(value('request.amount') ?? ''));
    if (amount === null || amount <= 0n)
      errors['request.amount'] =
        'Укажите положительную сумму в рублях, до двух знаков после запятой';
    else if (products.length) {
      const minimum = products.reduce((n, p) => {
        const v = parseMoney(p.minAmount)!;
        return v < n ? v : n;
      }, parseMoney(products[0].minAmount)!);
      const maximum = products.reduce((n, p) => {
        const v = parseMoney(p.maxAmount)!;
        return v > n ? v : n;
      }, parseMoney(products[0].maxAmount)!);
      if (amount < minimum || amount > maximum)
        errors['request.amount'] =
          `В каталоге доступны суммы от ${money(products.find((p) => parseMoney(p.minAmount) === minimum)!.minAmount)} до ${money(products.find((p) => parseMoney(p.maxAmount) === maximum)!.maxAmount)}. Измените сумму.`;
    }
    const term = value('request.termMonths');
    if (typeof term !== 'number' || !Number.isInteger(term) || term < 1 || term > 360)
      errors['request.termMonths'] = 'Укажите срок от 1 до 360 месяцев';
    const description = String(value('request.description') ?? '');
    if (description.length > 500 || /<[^>]*>/s.test(description))
      errors['request.description'] = 'Не больше 500 символов, без HTML';
  }
  if (stage === 2) {
    const hasRevenue = filled('financial.revenue');
    if (hasRevenue && parseMoney(String(value('financial.revenue'))) === null)
      errors['financial.revenue'] =
        'Укажите неотрицательную сумму в рублях, до двух знаков после запятой';
    const from = String(value('financial.periodFrom') ?? ''),
      to = String(value('financial.periodTo') ?? '');
    for (const path of ['financial.periodFrom', 'financial.periodTo']) checkDate(path);
    if (hasRevenue && !from)
      errors['financial.periodFrom'] = 'Укажите начало периода: без него нельзя оценить выручку';
    if (hasRevenue && !to)
      errors['financial.periodTo'] = 'Укажите конец периода: без него нельзя оценить выручку';
    if (from && to && from > to)
      errors['financial.periodTo'] = 'Конец периода должен быть не раньше начала';
    if (hasRevenue && validDate(from) && !from.endsWith('-01'))
      errors['financial.periodFrom'] = 'Выберите первое число месяца';
    if (hasRevenue && validDate(to)) {
      const end = new Date(to + 'T00:00:00Z');
      end.setUTCDate(end.getUTCDate() + 1);
      if (end.getUTCDate() !== 1) errors['financial.periodTo'] = 'Выберите последний день месяца';
    }
  }
  return errors;
}
