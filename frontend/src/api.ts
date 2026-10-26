export class ApiError extends Error {
  status: number;
  fields: string[];
  code: string;
  constructor(status: number, message: string, fields: string[] = [], code = '') {
    super(message);
    this.status = status;
    this.fields = fields;
    this.code = code;
  }
}

type Csrf = { headerName: string; token: string };
let csrf: Promise<Csrf> | undefined;
let sessionEpoch = 0;
export function clearApiSession() {
  sessionEpoch++;
  resetCsrf();
}
function requireSameSession(epoch: number) {
  if (epoch !== sessionEpoch)
    throw new ApiError(409, 'Сессия изменилась. Повторите действие.', [], 'SESSION_CHANGED');
}
export function resetCsrf() {
  csrf = undefined;
}

async function csrfHeaders(): Promise<Record<string, string>> {
  csrf ??= fetch('/api/auth/csrf', {
    credentials: 'same-origin',
    cache: 'no-store',
    signal: AbortSignal.timeout(25000),
  })
    .then(async (response) => {
      if (!response.ok)
        throw new ApiError(response.status, 'Не удалось защитить запрос. Повторите действие.');
      const value = (await response.json()) as Csrf;
      if (value.headerName !== 'X-XSRF-TOKEN' || !value.token)
        throw new Error('Invalid CSRF response');
      return value;
    })
    .catch((error) => {
      csrf = undefined;
      throw error;
    });
  const value = await csrf;
  return { [value.headerName]: value.token };
}

/** Credentials live only in HttpOnly cookies; CSRF headers only go to our same-origin Java API. */
export async function api<T>(
  path: string,
  body?: unknown,
  method = 'POST',
  extraHeaders: Record<string, string> = {},
): Promise<T> {
  if (
    !path.startsWith('/') ||
    path.startsWith('//') ||
    path.includes('\\') ||
    path.includes('#') ||
    path.includes('..')
  )
    throw new Error('Invalid API path');
  const epoch = sessionEpoch;
  const publicResponse =
    /^\/products(?:[/?]|$)/.test(path) || path === '/health' || path === '/auth/csrf';
  const verb = body === undefined ? 'GET' : method;
  const mutation = !['GET', 'HEAD', 'OPTIONS'].includes(verb);
  const multipart = body instanceof FormData;
  for (let attempt = 0; attempt < 2; attempt++) {
    let response: Response;
    try {
      const headers = {
        ...(!multipart && body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...extraHeaders,
        ...(mutation ? await csrfHeaders() : {}),
      };
      if (!publicResponse) requireSameSession(epoch);
      response = await fetch(`/api${path}`, {
        method: verb,
        credentials: 'same-origin',
        cache: 'no-store',
        signal: AbortSignal.timeout(25000),
        headers,
        ...(body !== undefined ? { body: multipart ? body : JSON.stringify(body) } : {}),
      });
    } catch (error) {
      if (error instanceof ApiError) throw error;
      throw new ApiError(
        0,
        'Не удалось связаться с сервисом. Проверьте подключение и попробуйте ещё раз.',
      );
    }
    const result = await response.json().catch(() => null);
    if (!publicResponse) requireSameSession(epoch);
    // CSRF rejection precedes controllers; retrying it cannot replay an executed mutation.
    if (response.status === 403 && result?.code === 'CSRF_INVALID' && mutation && attempt === 0) {
      resetCsrf();
      continue;
    }
    if (response.status === 401 && path !== '/auth/session' && path !== '/me') {
      resetCsrf();
      if (typeof window !== 'undefined') window.dispatchEvent(new Event('alpha-session-expired'));
    }
    if (!response.ok)
      throw new ApiError(
        response.status,
        result?.detail ??
          (response.status === 401
            ? 'Сессия завершилась. Войдите в кабинет снова.'
            : 'Не удалось выполнить действие. Попробуйте ещё раз.'),
        result?.fields ?? [],
        result?.code ?? '',
      );
    if (path === '/auth/session' || path === '/auth/logout') clearApiSession();
    return result as T;
  }
  throw new ApiError(403, 'Не удалось защитить запрос. Обновите страницу и попробуйте ещё раз.');
}

export async function upload(path: string, body: FormData): Promise<void> {
  await api(path, body);
}
