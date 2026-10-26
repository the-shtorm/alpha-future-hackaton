import type { Dictionaries, Product } from './types';

export const dictionaries: Dictionaries = {
  purposes: {
    WORKING_CAPITAL: 'Пополнение оборотных средств',
    CASH_GAP: 'Покрытие кассового разрыва',
    EQUIPMENT: 'Покупка оборудования',
    TRANSPORT: 'Покупка транспорта',
    COMMERCIAL_PROPERTY: 'Покупка недвижимости',
    CONTRACT_EXECUTION: 'Исполнение контракта',
    REFINANCING: 'Рефинансирование',
    DEVELOPMENT: 'Развитие бизнеса',
  },
  sectors: {
    TRADE: 'Торговля',
    MANUFACTURING: 'Производство',
    SERVICES: 'Услуги',
    IT: 'ИТ и разработка',
    CONSTRUCTION: 'Строительство',
    AGRICULTURE: 'Сельское хозяйство',
    LOGISTICS: 'Транспорт и логистика',
  },
  usageModes: {
    ONE_TIME: 'Одной суммой',
    IN_PARTS: 'Частями по мере необходимости',
    ACCOUNT_RESERVE: 'Резерв на расчётном счёте',
    UNKNOWN: 'Пока не определились',
  },
  readiness: {
    YES: 'Готовы обсудить',
    NO: 'Не готовы',
    DISCUSS: 'Нужно обсудить условия',
    UNKNOWN: 'Пока не знаем',
  },
};
export const purposeNames = dictionaries.purposes;
export const statusNames: Record<string, string> = {
  DRAFT: 'Черновик',
  SUBMITTED: 'Заявка отправлена',
  UNDER_REVIEW: 'На рассмотрении',
  NEEDS_INFO: 'Нужны сведения',
  APPROVED: 'Предложение готово',
  COUNTEROFFERED: 'Предложены другие условия',
  COUNTEROFFER: 'Предложены другие условия',
  DECLINED: 'Рассмотрение завершено',
  REJECTED: 'Рассмотрение завершено',
  OFFER_ACCEPTED: 'Предложение принято',
  SIGNED: 'Договор подписан',
  CONTRACT_SIGNED: 'Договор подписан',
  READY_FOR_DISBURSEMENT: 'Готова к выдаче',
  VALIDATING: 'Проверяем сведения',
  ENRICHING: 'Уточняем сведения',
  COMPLIANCE_REVIEW: 'Проверяем соответствие требованиям',
  LEGAL_REVIEW: 'Проверяем документы',
  SCORING: 'Оцениваем заявку',
  APPROVED_CONDITIONAL: 'Одобрена с условиями',
  OFFER_DECLINED: 'Предложение отклонено',
  EXPIRED: 'Срок предложения истёк',
  SERVICING: 'Кредит обслуживается',
  CLOSED: 'Заявка закрыта',
  DISBURSED: 'Средства перечислены',
  CANCELLED: 'Отменена',
};
export function money(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return 'Уточняются';
  const [whole, fraction = ''] = String(value).split('.');
  return `${whole.replace(/\B(?=(\d{3})+(?!\d))/g, '\u00a0')}${Number(fraction) ? ',' + fraction.padEnd(2, '0') : ''} ₽`;
}
export function rate(value: string | null): string {
  return value === null
    ? 'По условиям продукта'
    : `${value.includes('.') ? value.replace(/0+$/, '').replace(/\.$/, '') : value}%`;
}
export function months(value: number): string {
  const n = value % 100;
  return `${value} ${n >= 11 && n <= 14 ? 'месяцев' : value % 10 === 1 ? 'месяц' : value % 10 >= 2 && value % 10 <= 4 ? 'месяца' : 'месяцев'}`;
}
export function date(value: string): string {
  return new Intl.DateTimeFormat('ru-RU', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  }).format(new Date(value));
}
export function kind(product: Product): string {
  return (
    (
      {
        TERM: 'Кредит',
        REVOLVING_LINE: 'Возобновляемая линия',
        NON_REVOLVING_LINE: 'Кредитная линия',
        OVERDRAFT: 'Овердрафт',
      } as Record<string, string>
    )[product.policy.facility_kind ?? ''] ?? 'Финансирование'
  );
}
export function category(product: Product): string {
  if (product.purposes.includes('REFINANCING')) return 'refinancing';
  if (product.purposes.includes('COMMERCIAL_PROPERTY')) return 'property';
  if (
    product.purposes.some((p) =>
      ['EQUIPMENT', 'TRANSPORT', 'INVESTMENT', 'DEVELOPMENT'].includes(p),
    ) &&
    !product.purposes.includes('WORKING_CAPITAL')
  )
    return 'growth';
  return 'working';
}
export function parseMoney(value: string): bigint | null {
  const raw = value.replace(/[\s\u00a0₽]/g, '').replace(',', '.');
  if (!/^(?:0|[1-9]\d{0,16})(?:\.\d{1,2})?$/.test(raw)) return null;
  const [whole, cents = ''] = raw.split('.');
  return BigInt(whole) * 100n + BigInt(cents.padEnd(2, '0'));
}
export function matchesAmount(product: Product, input: string): boolean {
  if (!input.trim()) return true;
  const amount = parseMoney(input);
  return (
    amount !== null &&
    amount >= parseMoney(product.minAmount)! &&
    amount <= parseMoney(product.maxAmount)!
  );
}
