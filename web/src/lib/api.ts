import { useAuthStore } from '@/store/auth'
import type { ApiError } from '@/types/api'

const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:25001'

export class ApiRequestError extends Error {
  status: number
  detail: ApiError['detail']

  constructor(status: number, detail: ApiError['detail'], message: string) {
    super(message)
    this.name = 'ApiRequestError'
    this.status = status
    this.detail = detail
  }
}

interface RequestOptions {
  query?: Record<string, string | number | boolean | undefined>
  body?: unknown
  signal?: AbortSignal
  asPartner?: boolean
  asDevice?: boolean
}

function buildHeaders(opts: RequestOptions): Headers {
  const headers = new Headers()
  headers.set('Accept', 'application/json')
  if (opts.body !== undefined) headers.set('Content-Type', 'application/json')

  const auth = useAuthStore.getState()

  if (opts.asPartner) {
    if (!auth.partnerApiKey) throw new Error('partner api key required')
    headers.set('X-Partner-Api-Key', auth.partnerApiKey)
    return headers
  }

  if (opts.asDevice) {
    if (!auth.deviceKey) throw new Error('device key required')
    headers.set('X-Device-Key', auth.deviceKey)
    return headers
  }

  if (auth.role && auth.actorId) {
    headers.set('X-Role', auth.role)
    headers.set('X-Actor-Id', auth.actorId)
    if (auth.organizationId) headers.set('X-Organization-Id', auth.organizationId)
  }
  return headers
}

function buildQuery(query?: RequestOptions['query']): string {
  if (!query) return ''
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null) continue
    params.set(k, String(v))
  }
  const s = params.toString()
  return s ? `?${s}` : ''
}

async function request<T>(
  method: string,
  path: string,
  opts: RequestOptions = {},
): Promise<T> {
  const url = `${API_BASE_URL}${path}${buildQuery(opts.query)}`
  const init: RequestInit = {
    method,
    headers: buildHeaders(opts),
    signal: opts.signal,
  }
  if (opts.body !== undefined) init.body = JSON.stringify(opts.body)

  let res: Response
  try {
    res = await fetch(url, init)
  } catch (err) {
    throw new ApiRequestError(0, undefined, err instanceof Error ? err.message : 'network error')
  }

  if (res.status === 204) {
    return undefined as T
  }

  const text = await res.text()
  let parsed: unknown = null
  if (text) {
    try {
      parsed = JSON.parse(text)
    } catch {
      parsed = text
    }
  }

  if (!res.ok) {
    const detail = (parsed as ApiError | null)?.detail
    const message =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((d) => d.msg).join(', ')
          : `HTTP ${res.status}`
    throw new ApiRequestError(res.status, detail, message)
  }

  return parsed as T
}

export const api = {
  get: <T>(path: string, opts?: Omit<RequestOptions, 'body'>) => request<T>('GET', path, opts),
  post: <T>(path: string, body?: unknown, opts?: Omit<RequestOptions, 'body'>) =>
    request<T>('POST', path, { ...opts, body }),
  put: <T>(path: string, body?: unknown, opts?: Omit<RequestOptions, 'body'>) =>
    request<T>('PUT', path, { ...opts, body }),
  patch: <T>(path: string, body?: unknown, opts?: Omit<RequestOptions, 'body'>) =>
    request<T>('PATCH', path, { ...opts, body }),
  delete: <T>(path: string, opts?: Omit<RequestOptions, 'body'>) =>
    request<T>('DELETE', path, opts),
  baseUrl: API_BASE_URL,
}

// --- Bootstrap admin client (used pre-login to read demo data) -------------

const BOOTSTRAP_ID_KEY = 'omd-bootstrap-admin-id'

function getBootstrapAdminId(): string {
  let id = localStorage.getItem(BOOTSTRAP_ID_KEY)
  if (!id) {
    id = crypto.randomUUID()
    localStorage.setItem(BOOTSTRAP_ID_KEY, id)
  }
  return id
}

async function bootstrapRequest<T>(
  method: string,
  path: string,
  body?: unknown,
  query?: RequestOptions['query'],
): Promise<T> {
  const headers = new Headers({
    Accept: 'application/json',
    'X-Role': 'admin',
    'X-Actor-Id': getBootstrapAdminId(),
  })
  if (body !== undefined) headers.set('Content-Type', 'application/json')
  const url = `${API_BASE_URL}${path}${buildQuery(query)}`
  const init: RequestInit = { method, headers }
  if (body !== undefined) init.body = JSON.stringify(body)

  let res: Response
  try {
    res = await fetch(url, init)
  } catch (err) {
    throw new ApiRequestError(0, undefined, err instanceof Error ? err.message : 'network error')
  }
  if (res.status === 204) return undefined as T
  const text = await res.text()
  let parsed: unknown = null
  if (text) {
    try {
      parsed = JSON.parse(text)
    } catch {
      parsed = text
    }
  }
  if (!res.ok) {
    const detail = (parsed as ApiError | null)?.detail
    const message =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((d) => d.msg).join(', ')
          : `HTTP ${res.status}`
    throw new ApiRequestError(res.status, detail, message)
  }
  return parsed as T
}

export const bootstrapApi = {
  get: <T>(path: string, query?: RequestOptions['query']) =>
    bootstrapRequest<T>('GET', path, undefined, query),
  post: <T>(path: string, body?: unknown, query?: RequestOptions['query']) =>
    bootstrapRequest<T>('POST', path, body, query),
  adminId: getBootstrapAdminId,
}

export function formatApiError(err: unknown): string {
  if (err instanceof ApiRequestError) return err.message
  if (err instanceof Error) return err.message
  return '未知錯誤'
}
