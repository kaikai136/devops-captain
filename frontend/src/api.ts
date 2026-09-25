const JSON_HEADERS = { 'Content-Type': 'application/json' };
export const AUTH_EXPIRED_EVENT = 'ops-tool.auth.expired';

const AUTH_ENDPOINTS = ['/api/auth/login/', '/api/auth/login/2fa/', '/api/auth/login/2fa/setup/'];

export class ApiResponseError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly payload?: unknown,
  ) {
    super(message);
    this.name = 'ApiResponseError';
  }
}

export class ApiUnauthorizedError extends ApiResponseError {
  constructor(message: string) {
    super(message, 401);
    this.name = 'ApiUnauthorizedError';
  }
}

export async function apiGet<T>(url: string, options: RequestInit = {}): Promise<T> {
  return apiRequest<T>(url, options);
}

export async function apiPost<T>(url: string, payload: unknown, options: RequestInit = {}): Promise<T> {
  return apiJsonRequest<T>('POST', url, payload, options);
}

export async function apiPostForm<T>(url: string, body: FormData, options: RequestInit = {}): Promise<T> {
  return apiRequest<T>(url, { ...options, method: 'POST', body });
}

export async function apiPut<T>(url: string, payload: unknown, options: RequestInit = {}): Promise<T> {
  return apiJsonRequest<T>('PUT', url, payload, options);
}

export async function apiPatch<T>(url: string, payload: unknown, options: RequestInit = {}): Promise<T> {
  return apiJsonRequest<T>('PATCH', url, payload, options);
}

export async function apiDelete<T>(url: string, options: RequestInit = {}): Promise<T> {
  return apiRequest<T>(url, { method: 'DELETE', ...options });
}

async function apiJsonRequest<T>(method: string, url: string, payload: unknown, options: RequestInit = {}): Promise<T> {
  return apiRequest<T>(url, {
    ...options,
    method,
    headers: withJsonHeaders(options.headers),
    body: JSON.stringify(payload),
  });
}

async function apiRequest<T>(url: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(url, { credentials: 'include', ...options });
  return readResponse<T>(response, url);
}

async function readResponse<T>(response: Response, url: string): Promise<T> {
  const text = await response.text();
  const payload = parseResponsePayload(response, text);

  if (!response.ok) {
    const error = extractErrorMessage(payload) || '请求失败，请确认后端服务已启动';
    if (response.status === 401) {
      if (typeof window !== 'undefined' && !AUTH_ENDPOINTS.some((endpoint) => url.startsWith(endpoint))) {
        window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT));
      }
      throw new ApiUnauthorizedError(error);
    }
    throw new ApiResponseError(error, response.status, payload);
  }

  if (payload === null) {
    if (response.status === 204) return undefined as T;
    throw new Error('后端返回为空，请稍后重试');
  }

  return payload as T;
}

function parseResponsePayload(response: Response, text: string): unknown {
  if (!text) return null;

  try {
    return JSON.parse(text);
  } catch {
    if (response.ok) {
      throw new Error('后端返回了非 JSON 数据');
    }
    const contentType = response.headers.get('content-type') ?? '';
    const looksLikeHtml = contentType.includes('text/html') || /^\s*<!doctype html/i.test(text) || /^\s*<html/i.test(text);
    throw new Error(looksLikeHtml ? '后端服务异常，请确认数据库迁移已完成并查看后端日志' : text.slice(0, 240));
  }
}

function extractErrorMessage(payload: unknown) {
  if (!payload || typeof payload !== 'object') return '';
  const data = payload as Record<string, unknown>;
  for (const key of ['error', 'detail', 'message']) {
    if (typeof data[key] === 'string' && data[key]) return data[key];
  }
  return '';
}

function withJsonHeaders(headers?: HeadersInit) {
  const merged = new Headers(headers ?? JSON_HEADERS);
  if (!merged.has('Content-Type')) {
    merged.set('Content-Type', JSON_HEADERS['Content-Type']);
  }
  return merged;
}
