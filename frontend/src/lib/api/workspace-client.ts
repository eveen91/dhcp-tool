import type { components } from './schema';
export type Schema = components['schemas'];
export type ApiOptions = {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  body?: unknown;
  revision?: number;
  signal?: AbortSignal;
};
export type FieldErrors = Record<string, { code: string; message: string }[]>;
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public fields: FieldErrors = {},
    public currentRevision?: number,
    public retryAfter?: string,
  ) {
    super(message);
  }
}
export function createApiClient() {
  let token = '';
  async function request<T>(path: string, options: ApiOptions = {}): Promise<T> {
    const method = options.method ?? 'GET';
    let response: Response;
    try {
      response = await fetch(`/api/v1${path}`, {
        method,
        cache: 'no-store',
        credentials: 'same-origin',
        signal: options.signal,
        headers: {
          ...(options.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
          ...(method !== 'GET' ? { 'X-CSRFToken': token } : {}),
          ...(options.revision !== undefined
            ? { 'X-Config-Revision': String(options.revision) }
            : {}),
        },
        ...(options.body !== undefined ? { body: JSON.stringify(options.body) } : {}),
      });
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') throw error;
      throw new ApiError(
        0,
        'network_error',
        method === 'GET'
          ? 'Nie udało się pobrać danych. Ponów pobranie.'
          : 'Nie potwierdzono wyniku zapisu. Odśwież dane przed ponowieniem operacji.',
      );
    }
    if (response.status === 204) return undefined as T;
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = data?.error;
      throw new ApiError(
        response.status,
        typeof detail?.code === 'string' ? detail.code : 'api_error',
        typeof detail?.message === 'string'
          ? detail.message
          : 'Nie udało się wykonać operacji. Ponów pobranie danych.',
        detail?.fields ?? {},
        detail?.current_revision,
        response.headers.get('Retry-After') ?? undefined,
      );
    }
    if (data === null)
      throw new ApiError(502, 'invalid_response', 'Nie udało się odczytać odpowiedzi serwera.');
    return data as T;
  }
  async function session(signal?: AbortSignal) {
    const result = await request<Schema['Session']>('/auth/session/', { signal });
    token = result.csrf_token;
    return result;
  }
  async function login(body: Schema['Login']) {
    const result = await request<Schema['Session']>('/auth/session/', { method: 'POST', body });
    token = result.csrf_token;
    return result;
  }
  return {
    request,
    session,
    login,
    logout: () => request<void>('/auth/session/', { method: 'DELETE' }),
  };
}
export type ApiClient = ReturnType<typeof createApiClient>;
