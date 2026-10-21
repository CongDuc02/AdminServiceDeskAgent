// LỐI fetch DUY NHẤT (ADR-018; 06-structure.md mục 10): gắn X-BO19-CSRF cho mọi lệnh không phải GET, credentials same-origin, phân tích ErrorEnvelope,
// đọc body dạng stream. Luật ESLint cấm mọi file khác tham chiếu `fetch` (eslint.config.js).
//
// Luật 404 phía client (O1-8): một phản hồi 2xx mà không phải JSON ở chỗ chờ JSON (ví dụ `index.html` do route SPA nuốt) KHÔNG được đọc như dữ liệu — nó là lỗi
// `CLIENT_UNEXPECTED_RESPONSE`, không phải `{}`.
import type { components } from '@/api/generated/openapi'

export type ErrorEnvelope = components['schemas']['ErrorEnvelope']

export const API_PREFIX = '/api/v1'
export const CSRF_HEADER = 'X-BO19-CSRF'

/** Mã lỗi do CLIENT đặt khi không có ErrorEnvelope của server (mất mạng, phản hồi không phải JSON). Không nằm trong `ErrorCode` của contract. */
export type ClientErrorCode = 'CLIENT_NETWORK' | 'CLIENT_UNEXPECTED_RESPONSE'

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly envelope: ErrorEnvelope | null
  readonly headers: Headers

  constructor(status: number, code: string, message: string, envelope: ErrorEnvelope | null, headers: Headers) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.envelope = envelope
    this.headers = headers
  }

  get traceId(): string | null {
    return this.envelope?.trace_id ?? null
  }

  get details(): NonNullable<ErrorEnvelope['details']> {
    return this.envelope?.details ?? {}
  }

  /** `Retry-After` (giây) từ header, hoặc `details.retry_after_seconds`; `null` nếu không có. */
  get retryAfterSeconds(): number | null {
    const header = Number(this.headers.get('Retry-After'))
    if (this.headers.has('Retry-After') && Number.isFinite(header) && header >= 0) return header
    return this.details.retry_after_seconds ?? null
  }
}

let onUnauthenticated: (() => void) | null = null

/** App đăng ký một lần: gặp `UNAUTHENTICATED` ở bất kỳ response nào thì xoá bộ đệm, về trang đăng nhập (06-structure.md mục 11). */
export function setUnauthenticatedHandler(handler: (() => void) | null): void {
  onUnauthenticated = handler
}

export type RequestOptions = {
  query?: Record<string, string | number | undefined>
  body?: unknown
  headers?: Record<string, string>
  signal?: AbortSignal
}

function url(path: string, query?: RequestOptions['query']): string {
  const base = `${API_PREFIX}${path}`
  if (!query) return base
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(query)) if (v !== undefined) params.set(k, String(v))
  const qs = params.toString()
  return qs ? `${base}?${qs}` : base
}

function isJson(response: Response): boolean {
  return (response.headers.get('Content-Type') ?? '').toLowerCase().includes('json')
}

async function toError(response: Response): Promise<ApiError> {
  let envelope: ErrorEnvelope | null = null
  if (isJson(response)) {
    try {
      const body = (await response.json()) as Partial<ErrorEnvelope>
      if (typeof body?.error_code === 'string' && typeof body?.message === 'string') envelope = body as ErrorEnvelope
    } catch {
      envelope = null
    }
  }
  if (envelope) {
    if (envelope.error_code === 'UNAUTHENTICATED') onUnauthenticated?.()
    return new ApiError(response.status, envelope.error_code, envelope.message, envelope, response.headers)
  }
  return new ApiError(response.status, 'CLIENT_UNEXPECTED_RESPONSE', 'Hệ thống trả về phản hồi không đọc được. Vui lòng thử lại.', null, response.headers)
}

async function send(method: string, path: string, options: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = { Accept: 'application/json', ...options.headers }
  if (method !== 'GET') headers[CSRF_HEADER] = '1'
  let body: string | undefined
  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.body)
  }
  try {
    // URL tuyệt đối cùng origin với trang: chạy như đường dẫn tương đối ở trình duyệt, và cũng chạy được ở môi trường kiểm thử (fetch của Node không nhận đường dẫn tương đối).
    const target = new URL(url(path, options.query), globalThis.location.origin).href
    return await fetch(target, { method, headers, body, credentials: 'same-origin', signal: options.signal })
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e
    throw new ApiError(0, 'CLIENT_NETWORK', 'Không kết nối được tới hệ thống. Kiểm tra mạng rồi thử lại.', null, new Headers())
  }
}

/** JSON trả về (2xx). `T = void` cho 204. Lỗi → `ApiError` (rẽ nhánh theo `code`, không theo `message`). */
export async function request<T>(method: string, path: string, options: RequestOptions = {}): Promise<{ data: T; headers: Headers; status: number }> {
  const response = await send(method, path, options)
  if (!response.ok) throw await toError(response)
  if (response.status === 204) return { data: undefined as T, headers: response.headers, status: 204 }
  if (!isJson(response)) throw await toError(response)
  return { data: (await response.json()) as T, headers: response.headers, status: response.status }
}

export async function get<T>(path: string, options: RequestOptions = {}): Promise<T> {
  return (await request<T>('GET', path, options)).data
}

export async function post<T>(path: string, options: RequestOptions = {}): Promise<T> {
  return (await request<T>('POST', path, options)).data
}

export async function del<T>(path: string, options: RequestOptions = {}): Promise<T> {
  return (await request<T>('DELETE', path, options)).data
}

/** POST mà response là stream (lượt chat). 2xx → `Response` để người gọi đọc `body`; không-2xx → `ApiError` (JSON, trước khi stream bắt đầu). */
export async function postStream(path: string, options: RequestOptions = {}): Promise<Response> {
  const response = await send('POST', path, { ...options, headers: { ...options.headers, Accept: 'text/event-stream' } })
  if (!response.ok) throw await toError(response)
  if (!(response.headers.get('Content-Type') ?? '').toLowerCase().includes('text/event-stream') || !response.body) throw await toError(response)
  return response
}

/** GET tệp nhị phân (tải bản render). Lỗi `FILE_UNAVAILABLE` & co. đi thành `ApiError` mang `message` của server. */
export async function getBlob(path: string, options: RequestOptions = {}): Promise<{ blob: Blob; contentType: string; contentDisposition: string | null }> {
  const response = await send('GET', path, { ...options, headers: { ...options.headers, Accept: '*/*' } })
  if (!response.ok) throw await toError(response)
  if (isJson(response)) throw await toError(response) // 2xx mà là JSON: không phải tệp
  return { blob: await response.blob(), contentType: response.headers.get('Content-Type') ?? '', contentDisposition: response.headers.get('Content-Disposition') }
}
