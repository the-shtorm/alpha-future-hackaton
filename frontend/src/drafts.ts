import { normalizeAnswers, sameAnswers, emptyAnswers } from './form.ts';
import type { Answers } from './types';

const guestKey = 'alpha-guest-preliminary-v1';
const lifetime = 24 * 60 * 60 * 1000;
export function browserDraftStorage(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

/** Only preliminary form fields, in this tab, for 24 hours. Never credentials or account data. */
export function readGuestDraft(storage: Storage | null, now = Date.now()): Answers | null {
  try {
    const raw = storage?.getItem(guestKey);
    if (!raw) return null;
    if (raw.length > 16000) throw new Error('Oversized draft');
    const value = JSON.parse(raw);
    if (
      value.version !== 1 ||
      !Number.isFinite(value.savedAt) ||
      value.savedAt > now ||
      now - value.savedAt > lifetime ||
      !value.answers
    )
      throw new Error('Expired draft');
    const answers = structuredClone(emptyAnswers);
    for (const [section, fields] of Object.entries(answers)) {
      for (const key of Object.keys(fields)) {
        const item = value.answers[section]?.[key];
        if (
          item === null ||
          typeof item === 'boolean' ||
          (typeof item === 'number' && Number.isFinite(item)) ||
          (typeof item === 'string' && item.length <= (key === 'description' ? 500 : 120))
        ) {
          fields[key] = item;
        }
      }
    }
    return answers;
  } catch {
    clearGuestDraft(storage);
    return null;
  }
}

export function writeGuestDraft(
  storage: Storage | null,
  answers: Answers,
  now = Date.now(),
): boolean {
  try {
    const allowed: Answers = {};
    for (const [section, fields] of Object.entries(emptyAnswers)) {
      allowed[section] = Object.fromEntries(
        Object.keys(fields).map((key) => [key, answers[section]?.[key] ?? null]),
      );
    }
    if (!storage) return false;
    storage.setItem(guestKey, JSON.stringify({ version: 1, savedAt: now, answers: allowed }));
    return true;
  } catch {
    return false;
  }
}

export function clearGuestDraft(storage: Storage | null): void {
  try {
    storage?.removeItem(guestKey);
  } catch {
    /* Storage can be disabled by browser policy. */
  }
}

/** One writer per loaded draft. Versioned writes serialize without replacing newer editor input. */
export class DraftWriter<T extends { rowVersion: number; answers: Answers }> {
  current: T;
  blocked = false;
  private active = true;
  private queue: Promise<unknown> = Promise.resolve();
  private update: (current: T, answers: Answers) => Promise<T>;

  constructor(current: T, update: (current: T, answers: Answers) => Promise<T>) {
    this.current = current;
    this.update = update;
  }

  dispose() {
    this.active = false;
  }

  save(answers: Answers): Promise<T> {
    const payload = structuredClone(normalizeAnswers(answers));
    const pending = this.queue
      .catch(() => undefined)
      .then(async () => {
        if (!this.active) throw new Error('Эта форма уже закрыта.');
        if (this.blocked)
          throw new Error('Заявка изменена в другой вкладке. Загрузите актуальную версию.');
        if (sameAnswers(this.current.answers, payload)) return this.current;
        try {
          const updated = await this.update(this.current, payload);
          if (!this.active) throw new Error('Эта форма уже закрыта.');
          this.current = updated;
          return updated;
        } catch (error) {
          if (error && typeof error === 'object' && 'status' in error && error.status === 409)
            this.blocked = true;
          throw error;
        }
      });
    this.queue = pending;
    return pending;
  }
}
