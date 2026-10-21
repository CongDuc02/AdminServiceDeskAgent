// Lối fetch duy nhất (ADR-018): CSRF chỉ cho lệnh không phải GET, credentials same-origin, phân tích ErrorEnvelope, luật 404 phía client (O1-8: HTML ở chỗ chờ JSON là lỗi).
import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ENVELOPE } from '@/test/fixtures'
import { server } from '@/test/server'
import { ApiError, del, get, getBlob, post, postStream, setUnauthenticatedHandler } from './http'

afterEach(() => setUnauthenticatedHandler(null))

describe('header và cookie', () => {
  it('GET không gắn X-BO19-CSRF; POST, DELETE có', async () => {
    const seen: Record<string, string | null> = {}
    server.use(
      http.get('/api/v1/x', ({ request }) => {
        seen.get = request.headers.get('X-BO19-CSRF')
        return HttpResponse.json({ ok: true })
      }),
      http.post('/api/v1/x', ({ request }) => {
        seen.post = request.headers.get('X-BO19-CSRF')
        return HttpResponse.json({ ok: true })
      }),
      http.delete('/api/v1/x', ({ request }) => {
        seen.del = request.headers.get('X-BO19-CSRF')
        return new HttpResponse(null, { status: 204 })
      }),
    )
    await get('/x')
    await post('/x', { body: { a: 1 } })
    await del('/x')
    expect(seen).toEqual({ get: null, post: '1', del: '1' })
  })

  it('gửi JSON, Idempotency-Key và query; bỏ tham số undefined', async () => {
    let seen: { url: string; key: string | null; body: unknown; type: string | null } | null = null
    server.use(
      http.post('/api/v1/y', async ({ request }) => {
        seen = { url: request.url, key: request.headers.get('Idempotency-Key'), body: await request.json(), type: request.headers.get('Content-Type') }
        return HttpResponse.json({ ok: true })
      }),
    )
    await post('/y', { body: { text: 'xin chào' }, headers: { 'Idempotency-Key': 'k-1' }, query: { a: 1, b: undefined } })
    expect(seen).toMatchObject({ key: 'k-1', body: { text: 'xin chào' }, type: 'application/json' })
    expect(new URL(seen!.url).search).toBe('?a=1')
  })

  it('credentials same-origin', async () => {
    let credentials: string | null = null
    server.use(
      http.get('/api/v1/z', ({ request }) => {
        credentials = request.credentials
        return HttpResponse.json({})
      }),
    )
    await get('/z')
    expect(credentials).toBe('same-origin')
  })
})

describe('lỗi', () => {
  it('ErrorEnvelope thành ApiError với mã, thông điệp NGUYÊN VĂN, trace_id và details', async () => {
    server.use(http.get('/api/v1/e', () => HttpResponse.json(ENVELOPE('STATE_CONFLICT', 'Yêu cầu đã đổi trạng thái.', { current_status: 'SUBMITTED' }), { status: 409 })))
    const err = (await get('/e').catch((e: unknown) => e)) as ApiError
    expect(err).toBeInstanceOf(ApiError)
    expect([err.status, err.code, err.message, err.traceId, err.details.current_status]).toEqual([409, 'STATE_CONFLICT', 'Yêu cầu đã đổi trạng thái.', '123e4567-e89b-42d3-a456-426614174000', 'SUBMITTED'])
  })

  it('Retry-After lấy từ header, rồi từ details.retry_after_seconds', async () => {
    server.use(
      http.get('/api/v1/r1', () => HttpResponse.json(ENVELOPE('TURN_NOT_FINISHED', 'm'), { status: 409, headers: { 'Retry-After': '7' } })),
      http.get('/api/v1/r2', () => HttpResponse.json(ENVELOPE('TURN_NOT_FINISHED', 'm', { retry_after_seconds: 4 }), { status: 409 })),
      http.get('/api/v1/r3', () => HttpResponse.json(ENVELOPE('TURN_NOT_FINISHED', 'm'), { status: 409 })),
    )
    expect(((await get('/r1').catch((e: unknown) => e)) as ApiError).retryAfterSeconds).toBe(7)
    expect(((await get('/r2').catch((e: unknown) => e)) as ApiError).retryAfterSeconds).toBe(4)
    expect(((await get('/r3').catch((e: unknown) => e)) as ApiError).retryAfterSeconds).toBeNull()
  })

  it('UNAUTHENTICATED gọi bộ xử lý; INVALID_CREDENTIALS thì không', async () => {
    const handler = vi.fn()
    setUnauthenticatedHandler(handler)
    server.use(
      http.get('/api/v1/u', () => HttpResponse.json(ENVELOPE('UNAUTHENTICATED', 'Phiên đã hết hạn.'), { status: 401 })),
      http.post('/api/v1/auth/session', () => HttpResponse.json(ENVELOPE('INVALID_CREDENTIALS', 'Mã nhân viên hoặc mật khẩu không đúng.'), { status: 401 })),
    )
    await get('/u').catch(() => undefined)
    expect(handler).toHaveBeenCalledTimes(1)
    await post('/auth/session', { body: {} }).catch(() => undefined)
    expect(handler).toHaveBeenCalledTimes(1)
  })

  it('mất mạng → CLIENT_NETWORK', async () => {
    server.use(http.get('/api/v1/n', () => HttpResponse.error()))
    const err = (await get('/n').catch((e: unknown) => e)) as ApiError
    expect([err.code, err.status]).toEqual(['CLIENT_NETWORK', 0])
  })
})

describe('luật 404 phía client (O1-8)', () => {
  it('2xx mà là HTML (index.html bị route SPA nuốt) KHÔNG được đọc như JSON', async () => {
    server.use(http.get('/api/v1/h', () => new HttpResponse('<!doctype html><html></html>', { status: 200, headers: { 'Content-Type': 'text/html' } })))
    const err = (await get('/h').catch((e: unknown) => e)) as ApiError
    expect([err.code, err.status]).toEqual(['CLIENT_UNEXPECTED_RESPONSE', 200])
  })

  it('lỗi không phải envelope (ví dụ {"detail":"Not Found"}) → CLIENT_UNEXPECTED_RESPONSE, không lộ thân', async () => {
    server.use(http.get('/api/v1/d', () => HttpResponse.json({ detail: 'Not Found' }, { status: 404 })))
    const err = (await get('/d').catch((e: unknown) => e)) as ApiError
    expect([err.code, err.status, err.envelope]).toEqual(['CLIENT_UNEXPECTED_RESPONSE', 404, null])
    expect(err.message).not.toContain('Not Found')
  })

  it('204 trả undefined', async () => {
    server.use(http.post('/api/v1/auth/session', () => new HttpResponse(null, { status: 204 })))
    expect(await post('/auth/session', { body: {} })).toBeUndefined()
  })
})

describe('stream và tệp', () => {
  it('postStream: 2xx text/event-stream → Response; 409 JSON → ApiError', async () => {
    server.use(
      http.post('/api/v1/s', () => new HttpResponse('event: turn.reply\ndata: {}\n\n', { headers: { 'Content-Type': 'text/event-stream' } })),
      http.post('/api/v1/s2', () => HttpResponse.json(ENVELOPE('TURN_IN_PROGRESS', 'Lượt trước chưa xong.'), { status: 409 })),
      http.post('/api/v1/s3', () => HttpResponse.json({ ok: true })),
    )
    const response = await postStream('/s', { body: {} })
    expect(await response.text()).toContain('turn.reply')
    expect(((await postStream('/s2', { body: {} }).catch((e: unknown) => e)) as ApiError).code).toBe('TURN_IN_PROGRESS')
    expect(((await postStream('/s3', { body: {} }).catch((e: unknown) => e)) as ApiError).code).toBe('CLIENT_UNEXPECTED_RESPONSE')
  })

  it('getBlob: trả byte; FILE_UNAVAILABLE giữ thông điệp của server', async () => {
    server.use(
      http.get('/api/v1/f1', () => new HttpResponse(new Uint8Array([37, 80, 68, 70]), { headers: { 'Content-Type': 'application/pdf', 'Content-Disposition': 'attachment; filename="x.pdf"' } })),
      http.get('/api/v1/f2', () => HttpResponse.json(ENVELOPE('FILE_UNAVAILABLE', 'Tệp tạm thời không tải được.'), { status: 503 })),
    )
    const ok = await getBlob('/f1')
    expect([ok.contentType, ok.blob.size, ok.contentDisposition]).toEqual(['application/pdf', 4, 'attachment; filename="x.pdf"'])
    const err = (await getBlob('/f2').catch((e: unknown) => e)) as ApiError
    expect([err.code, err.status, err.message]).toEqual(['FILE_UNAVAILABLE', 503, 'Tệp tạm thời không tải được.'])
  })

  it('getBlob: 2xx mà là JSON (không phải tệp) bị từ chối — không lưu JSON thành "PDF"', async () => {
    server.use(http.get('/api/v1/f3', () => HttpResponse.json({ ok: true })))
    const err = (await getBlob('/f3').catch((e: unknown) => e)) as ApiError
    expect([err.code, err.status]).toEqual(['CLIENT_UNEXPECTED_RESPONSE', 200])
  })
})
