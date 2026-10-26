import { useState, type Dispatch, type SetStateAction } from 'react';
import { Textarea } from '@alfalab/core-components-textarea';
import type { Answers, Dictionaries, Product } from '../types';
import { money, purposeNames } from '../presentation';
import { validatePreliminary } from '../validation';
import { Banner, Button, Field, Icon, Select } from './UI';

const labels = ['О компании', 'Ваша задача', 'Проверка условий'];
export function Wizard({
  answers,
  setAnswers,
  businessKindLocked,
  onBack,
  onSubmit,
  busy,
  dictionary,
  products,
}: {
  answers: Answers;
  setAnswers: Dispatch<SetStateAction<Answers>>;
  businessKindLocked: boolean;
  onBack: () => void;
  onSubmit: () => void;
  busy: boolean;
  dictionary: Dictionaries;
  products: Product[];
}) {
  const [step, setStep] = useState(0),
    [errors, setErrors] = useState<Record<string, string>>({});
  const value = (path: string) => {
    const [s, k] = path.split('.');
    return answers[s]?.[k] ?? '';
  };
  const set = (path: string, v: string | number | boolean | null) => {
    const [s, k] = path.split('.');
    setAnswers((current) => ({ ...current, [s]: { ...current[s], [k]: v } }));
    setErrors((old) => {
      const next = { ...old };
      delete next[path];
      return next;
    });
  };
  const input = (
    path: string,
    label: string,
    type: 'text' | 'number' | 'date' = 'text',
    hint?: string,
  ) => (
    <Field
      key={path}
      label={label}
      type={type}
      value={String(value(path))}
      onChange={(v) => set(path, type === 'number' ? (v === '' ? null : Number(v)) : v)}
      hint={hint}
      error={errors[path]}
    />
  );
  const select = (path: string, label: string, options: Record<string, string>) => (
    <Select
      key={path}
      label={label}
      value={String(value(path))}
      options={options}
      onChange={(v) => set(path, v)}
      error={errors[path]}
    />
  );
  const move = () => {
    const next = validatePreliminary(answers, products, step);
    setErrors(next);
    if (Object.keys(next).length) {
      if (
        step === 2 &&
        (next['request.amount'] || next['request.termMonths'] || next['request.description'])
      )
        setStep(1);
      return;
    }
    if (step < 2) {
      setStep(step + 1);
      window.scrollTo({ top: 0, behavior: 'instant' });
    } else onSubmit();
  };
  return (
    <section className="wizard-page">
      <button className="back-link" disabled={busy} onClick={onBack}>
        <Icon name="back" size={17} />К каталогу
      </button>
      <div className="page-heading">
        <span className="eyebrow">ПОДБОР ФИНАНСИРОВАНИЯ</span>
        <h1>
          Расскажите, что нужно
          <br />
          вашему бизнесу.
        </h1>
        <p>Проверим условия продуктов и сохраним подходящие варианты в кабинете.</p>
      </div>
      <div className="wizard-layout">
        <form
          className="wizard-panel"
          onSubmit={(e) => {
            e.preventDefault();
            move();
          }}
        >
          <fieldset disabled={busy}>
            <div className="wizard-progress" aria-label="Этапы формы">
              {labels.map((name, i) => (
                <div className={i === step ? 'current' : i < step ? 'complete' : ''} key={name}>
                  <span>{i < step ? <Icon name="check" size={15} /> : i + 1}</span>
                  <p>{name}</p>
                </div>
              ))}
            </div>
            <div className="wizard-step-content" key={step}>
              <div className="wizard-step-heading">
                <span>ШАГ {step + 1} ИЗ 3</span>
                <h2>
                  {step === 0
                    ? 'Сначала познакомимся'
                    : step === 1
                      ? 'На что нужны деньги?'
                      : 'Осталось уточнить условия'}
                </h2>
                <p>
                  {step === 0
                    ? 'Информация о компании нужна для проверки ограничений продуктов.'
                    : step === 1
                      ? 'Выберите цель и удобный способ использования средств.'
                      : 'Неизвестные значения можно оставить пустыми. Уточним их при оформлении.'}
                </p>
              </div>
              {step === 0 && (
                <>
                  <div className="business-kind">
                    <span>Форма бизнеса</span>
                    <div role="group" aria-label="Форма бизнеса">
                      {[
                        ['LLC', 'ООО'],
                        ['IP', 'ИП'],
                      ].map(([key, text]) => (
                        <button
                          type="button"
                          aria-pressed={value('registration.borrowerKind') === key}
                          key={key}
                          disabled={businessKindLocked}
                          onClick={() =>
                            setAnswers({
                              ...answers,
                              registration: { ...answers.registration, borrowerKind: key },
                              business: {
                                ...answers.business,
                                taxRegime:
                                  key === 'LLC' &&
                                  ['PSN', 'NPD'].includes(String(value('business.taxRegime')))
                                    ? 'UNKNOWN'
                                    : answers.business.taxRegime,
                              },
                            })
                          }
                        >
                          {text}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="fields-grid">
                    {select('business.sector', 'Сфера деятельности', {
                      '': 'Пока не знаю',
                      ...dictionary.sectors,
                    })}
                    {select('business.taxRegime', 'Система налогообложения', {
                      UNKNOWN: 'Пока не знаю',
                      USN: 'УСН',
                      OSNO: 'ОСНО',
                      AUSN: 'АУСН',
                      ...(value('registration.borrowerKind') === 'IP'
                        ? { PSN: 'Патент', NPD: 'Налог на профессиональный доход' }
                        : {}),
                    })}
                    {input('business.actualStartedOn', 'Когда начали работать', 'date')}
                    <Select
                      label="Компания в реестре МСП"
                      value={String(value('business.mspRegistry'))}
                      options={{ '': 'Пока не знаю', true: 'Да', false: 'Нет' }}
                      onChange={(v) => set('business.mspRegistry', v === '' ? null : v === 'true')}
                    />
                  </div>
                  <div className="quiet-note">
                    <Icon name="shield" size={18} />
                    <p>
                      Стаж бизнеса считаем от фактического начала работы. Неизвестные сведения можно
                      уточнить позже.
                    </p>
                  </div>
                </>
              )}
              {step === 1 && (
                <>
                  {select('request.purpose', 'Цель финансирования', dictionary.purposes)}
                  <div className="fields-grid form-spaced">
                    {input(
                      'request.amount',
                      'Сумма финансирования, ₽',
                      'text',
                      'Для кредитной линии — размер лимита',
                    )}
                    {input('request.termMonths', 'Срок, месяцев', 'number')}
                  </div>
                  <h3 className="field-heading">Как планируете использовать деньги?</h3>
                  <div
                    className="usage-options"
                    role="group"
                    aria-label="Способ использования средств"
                  >
                    {Object.entries(dictionary.usageModes).map(([key, text]) => (
                      <button
                        className={value('request.usageMode') === key ? 'selected' : ''}
                        type="button"
                        aria-pressed={value('request.usageMode') === key}
                        onClick={() => set('request.usageMode', key)}
                        key={key}
                      >
                        <span className="radio-dot" />
                        <strong>{text}</strong>
                        <small>
                          {key === 'ONE_TIME'
                            ? 'Одна выдача на конкретную задачу'
                            : key === 'IN_PARTS'
                              ? 'По мере необходимости'
                              : key === 'ACCOUNT_RESERVE'
                                ? 'На случай нехватки денег'
                                : 'Поможем определиться'}
                        </small>
                      </button>
                    ))}
                  </div>
                  <Textarea
                    label="Расскажите о задаче — по желанию"
                    block
                    minRows={3}
                    maxLength={500}
                    value={String(value('request.description'))}
                    error={errors['request.description']}
                    hint="До 500 символов. Не указывайте персональные данные."
                    onChange={(e) => set('request.description', e.target.value)}
                    placeholder="Например, хочу закупать товар небольшими партиями перед сезоном"
                  />
                </>
              )}
              {step === 2 && (
                <>
                  <div className="subsection-title">
                    <Icon name="wallet" />
                    <div>
                      <h3>Выручка компании</h3>
                      <p>Используем для проверки условий продукта. Это не сумма кредита.</p>
                    </div>
                  </div>
                  {input(
                    'financial.revenue',
                    'Выручка за выбранный период, ₽',
                    'text',
                    'Если сумма неизвестна, оставьте поле пустым',
                  )}
                  <div className="fields-grid form-spaced">
                    {input('financial.periodFrom', 'Начало периода', 'date')}
                    {input('financial.periodTo', 'Конец периода', 'date')}
                  </div>
                  <div className="subsection-title">
                    <Icon name="shield" />
                    <div>
                      <h3>Обеспечение</h3>
                      <p>
                        Готовность к обсуждению ещё не означает наличие проверенного залога или
                        поручителя.
                      </p>
                    </div>
                  </div>
                  <div className="fields-grid">
                    {select(
                      'security.collateralReady',
                      'Имущественный залог',
                      dictionary.readiness,
                    )}
                    {select('security.guarantorReady', 'Поручительство', dictionary.readiness)}
                  </div>
                </>
              )}
            </div>
            {!!Object.keys(errors).length && (
              <Banner tone="error">Проверьте отмеченные поля.</Banner>
            )}
            <div className="wizard-bottom">
              <Button
                view="transparent"
                size={48}
                type="button"
                leftAddons={<Icon name="back" size={17} />}
                onClick={() => {
                  if (step) setStep(step - 1);
                  else onBack();
                }}
              >
                {step ? 'Назад' : 'К каталогу'}
              </Button>
              <Button
                view="accent"
                size={56}
                type="submit"
                loading={busy}
                rightAddons={<Icon name="arrow" size={18} />}
              >
                {step === 2 ? 'Показать предложения' : 'Продолжить'}
              </Button>
            </div>
          </fieldset>
        </form>
        <aside className="wizard-aside">
          <div className="summary-card">
            <span className="summary-label">ВАША ЗАДАЧА</span>
            <h3>
              {value('request.amount')
                ? money(String(value('request.amount')))
                : 'Всё начинается с цели'}
            </h3>
            <p>{purposeNames[String(value('request.purpose'))]}</p>
            <dl>
              <div>
                <dt>Срок</dt>
                <dd>{String(value('request.termMonths'))} мес.</dd>
              </div>
              <div>
                <dt>Использование</dt>
                <dd>{dictionary.usageModes[String(value('request.usageMode'))]}</dd>
              </div>
            </dl>
          </div>
          <div className="aside-help">
            <Icon name="shield" size={25} />
            <h3>Решение остаётся за вами</h3>
            <p>
              Заполнение формы не отправляет заявку на кредит. Сначала вы увидите варианты и сможете
              изучить условия.
            </p>
            <div>
              <Icon name="check" size={16} />
              Сохранённые результаты в кабинете
            </div>
            <div>
              <Icon name="check" size={16} />
              Понятные условия для каждого продукта
            </div>
          </div>
        </aside>
      </div>
    </section>
  );
}
