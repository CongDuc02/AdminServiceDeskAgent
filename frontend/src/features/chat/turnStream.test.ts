// Stream lượt chat và LUẬT DỰNG LẠI (ADR-018): từng nhánh một, qua tầng mạng giả (MSW) — lối fetch thật vẫn chạy.
import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import { ENVELOPE, SESSION, message } from '@/test/fixtures'
import { server } from '@/test/server'
import { findTurnReply, sendTurn, type TurnEvent } from './turnStream'

const MSG_ID = '99999999-9999-4999-8999-999999999999'
const sse = (...events: [string, unknown][]) => events.map(([e, d]) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`).join('')
const stream = (body: string) => new HttpResponse(body, { headers: { 'Content-Type': 'text/event-stream' } })
const employee = message(10, 'EMPLOYEE', 'Tôi cần giấy xác nhận công tác', MSG_ID)
const agent = message(11, 'AGENT', 'Mình đã mở yêu cầu cho bạn.')
const reply = { message: agent, active_request: null, pending_question: null }

const turnUrl = `/api/v1/chat-sessions/${SESSION.id}/turns`
const messagesUrl = `/api/v1/chat-sessions/${SESSION.id}/messages`
const page = (...items: ReturnType<typeof message>[]) => HttpResponse.json({ items: [...items].sort((a, b) => b.seq - a.seq), next_cursor: null })
const run = (over: Partial<Parameters<typeof sendTurn>[0]> = {}) => sendTurn({ sessionId: SESSION.id, text: employee.body!, messageId: MSG_ID, sleep: async () => {}, ...over })

describe('đường thẳng', () => {
  it('accepted → progress → reply: gọi onEvent đúng thứ tự, gửi Idempotency-Key = id tin nhắn', async () => {
    let key: string | null = null
    let accept: string | null = null
    server.use(
      http.post(turnUrl, ({ request }) => {
        key = request.headers.get('Idempotency-Key')
        accept = request.headers.get('Accept')
        return stream(sse(['turn.accepted', { message: employee }], ['turn.progress', { stage: 'UNDERSTANDING' }], ['turn.progress', { stage: 'PREPARING_REPLY' }], ['turn.reply', reply]))
      }),
    )
    const events: TurnEvent[] = []
    const out = await run({ onEvent: (e) => events.push(e) })
    expect(out).toEqual({ kind: 'reply', reply })
    expect(events).toEqual([{ type: 'accepted', message: employee }, { type: 'progress', stage: 'UNDERSTANDING' }, { type: 'progress', stage: 'PREPARING_REPLY' }])
    expect([key, accept]).toEqual([MSG_ID, 'text/event-stream'])
  })

  it('gửi lại cùng khoá, tin agent đã có: stream accepted + reply đọc từ DB (Idempotent-Replayed)', async () => {
    server.use(http.post(turnUrl, () => new HttpResponse(sse(['turn.accepted', { message: employee }], ['turn.reply', reply]), { headers: { 'Content-Type': 'text/event-stream', 'Idempotent-Replayed': 'true' } })))
    expect(await run()).toEqual({ kind: 'reply', reply })
  })
})

describe('lỗi trước khi stream bắt đầu → ném nguyên ErrorEnvelope, KHÔNG dựng lại', () => {
  it.each([['TURN_IN_PROGRESS', 409], ['CHAT_SESSION_CLOSED', 409], ['PERMISSION_DENIED', 403], ['PAYLOAD_TOO_LARGE', 413]])('%s', async (code, status) => {
    server.use(http.post(turnUrl, () => HttpResponse.json(ENVELOPE(code, 'Thông điệp của server.'), { status })), http.get(messagesUrl, () => { throw new Error('không được gọi GET messages') }))
    await expect(run()).rejects.toMatchObject({ code, message: 'Thông điệp của server.' })
  })
})

describe('turn.error giữa stream', () => {
  it('ném ApiError mang envelope', async () => {
    server.use(http.post(turnUrl, () => stream(sse(['turn.accepted', { message: employee }], ['turn.error', ENVELOPE('INTERNAL_ERROR', 'Hệ thống đang bận.')]))))
    await expect(run()).rejects.toMatchObject({ code: 'INTERNAL_ERROR', message: 'Hệ thống đang bận.' })
  })
})

describe('stream đứt trước turn.reply — luật dựng lại', () => {
  it('(2) tin agent đã có trong chat_message → hiển thị nó, KHÔNG gửi lại', async () => {
    let posts = 0
    server.use(
      http.post(turnUrl, () => {
        posts++
        return stream(sse(['turn.accepted', { message: employee }], ['turn.progress', { stage: 'UNDERSTANDING' }])) // đứt: không có reply
      }),
      http.get(messagesUrl, () => page(employee, agent)),
    )
    const out = await run()
    expect(out).toEqual({ kind: 'recovered', employee, agent })
    expect(posts).toBe(1)
  })

  it('(3) chưa có → gửi lại CÙNG khoá → reply', async () => {
    const keys: (string | null)[] = []
    server.use(
      http.post(turnUrl, ({ request }) => {
        keys.push(request.headers.get('Idempotency-Key'))
        return keys.length === 1 ? stream(sse(['turn.accepted', { message: employee }])) : stream(sse(['turn.accepted', { message: employee }], ['turn.reply', reply]))
      }),
      http.get(messagesUrl, () => page(employee)),
    )
    expect(await run()).toEqual({ kind: 'reply', reply })
    expect(keys).toEqual([MSG_ID, MSG_ID])
  })

  it('tin nhân viên chưa tới server (đứt rất sớm): GET không thấy → gửi lại cùng khoá', async () => {
    let posts = 0
    server.use(
      http.post(turnUrl, () => (++posts === 1 ? stream('') : stream(sse(['turn.accepted', { message: employee }], ['turn.reply', reply])))),
      http.get(messagesUrl, () => page(message(5, 'AGENT', 'tin cũ'))),
    )
    expect(await run()).toEqual({ kind: 'reply', reply })
    expect(posts).toBe(2)
  })

  it('mất mạng ở POST đầu → coi như đứt, dựng lại', async () => {
    let posts = 0
    server.use(
      http.post(turnUrl, () => (++posts === 1 ? HttpResponse.error() : stream(sse(['turn.accepted', { message: employee }], ['turn.reply', reply])))),
      http.get(messagesUrl, () => page()),
    )
    expect(await run()).toEqual({ kind: 'reply', reply })
  })

  it('409 TURN_NOT_FINISHED, turn_abandoned = false: chờ theo Retry-After rồi quay lại bước 1 (GET) → tìm thấy tin agent', async () => {
    const sleeps: number[] = []
    let posts = 0
    let gets = 0
    server.use(
      http.post(turnUrl, () => {
        posts++
        return posts === 1 ? stream(sse(['turn.accepted', { message: employee }])) : HttpResponse.json(ENVELOPE('TURN_NOT_FINISHED', 'Tin nhắn đã được lưu.', { message_saved: true, turn_abandoned: false }), { status: 409, headers: { 'Retry-After': '3' } })
      }),
      http.get(messagesUrl, () => (++gets <= 1 ? page(employee) : page(employee, agent))),
    )
    const out = await run({ sleep: async (s) => void sleeps.push(s) })
    expect(out).toEqual({ kind: 'recovered', employee, agent })
    expect(sleeps).toEqual([3])
    expect([posts, gets]).toEqual([2, 2])
  })

  it('409 TURN_NOT_FINISHED, turn_abandoned = true: hiển thị ĐÚNG message của server, không thử lại', async () => {
    let posts = 0
    server.use(
      http.post(turnUrl, () => {
        posts++
        return posts === 1 ? stream('') : HttpResponse.json(ENVELOPE('TURN_NOT_FINISHED', 'Tin nhắn của bạn đã được lưu nhưng hệ thống không trả lời được. Vui lòng gửi lại.', { message_saved: true, turn_abandoned: true }), { status: 409 })
      }),
      http.get(messagesUrl, () => page(employee)),
    )
    const out = await run()
    expect(out.kind).toBe('abandoned')
    expect(out.kind === 'abandoned' && out.error.message).toBe('Tin nhắn của bạn đã được lưu nhưng hệ thống không trả lời được. Vui lòng gửi lại.')
    expect(posts).toBe(2)
  })

  it('Retry-After quá lớn bị chặn ở 10 s; thiếu thì dùng 2 s', async () => {
    const sleeps: number[] = []
    let posts = 0
    const unfinished = (retry?: string) => HttpResponse.json(ENVELOPE('TURN_NOT_FINISHED', 'm', { turn_abandoned: false }), { status: 409, headers: retry ? { 'Retry-After': retry } : {} })
    server.use(
      http.post(turnUrl, () => (++posts === 1 ? unfinished('600') : posts === 2 ? unfinished() : stream(sse(['turn.reply', reply])))),
      http.get(messagesUrl, () => page(employee)),
    )
    expect((await run({ sleep: async (s) => void sleeps.push(s) })).kind).toBe('reply')
    expect(sleeps).toEqual([10, 2])
  })

  it('không dựng lại mãi: hết số vòng thì gave_up', async () => {
    server.use(http.post(turnUrl, () => HttpResponse.json(ENVELOPE('TURN_NOT_FINISHED', 'm', { turn_abandoned: false }), { status: 409 })), http.get(messagesUrl, () => page(employee)))
    const sleep = vi.fn(async () => {})
    expect(await run({ sleep })).toEqual({ kind: 'gave_up' })
    expect(sleep.mock.calls.length).toBeGreaterThan(5)
    expect(sleep.mock.calls.length).toBeLessThanOrEqual(12)
  })

  it('lỗi lạ khi gửi lại (ví dụ UNAUTHENTICATED) được ném, không nuốt', async () => {
    let posts = 0
    server.use(
      http.post(turnUrl, () => (++posts === 1 ? stream('') : HttpResponse.json(ENVELOPE('UNAUTHENTICATED', 'Phiên đã hết hạn.'), { status: 401 }))),
      http.get(messagesUrl, () => page(employee)),
    )
    await expect(run()).rejects.toMatchObject({ code: 'UNAUTHENTICATED' })
  })
})

describe('findTurnReply', () => {
  const list = (...m: ReturnType<typeof message>[]) => [...m].sort((a, b) => b.seq - a.seq) // API trả giảm dần
  it('tin agent đầu tiên sau tin nhân viên', () => {
    expect(findTurnReply(list(message(1, 'AGENT', 'x'), employee, agent), MSG_ID)).toEqual({ employee, agent })
  })
  it('có tin nhân viên khác chen giữa → không đoán', () => {
    expect(findTurnReply(list(employee, message(11, 'EMPLOYEE', 'tin sau'), message(12, 'AGENT', 'trả lời tin sau')), MSG_ID)).toBeNull()
  })
  it('không có tin nhân viên đó → null; chưa có agent sau → null', () => {
    expect(findTurnReply(list(agent), MSG_ID)).toBeNull()
    expect(findTurnReply(list(employee), MSG_ID)).toBeNull()
  })
})
