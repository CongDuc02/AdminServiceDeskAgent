// ChatPage: mở phiên, hiện lịch sử đúng thứ tự, gửi một lượt, đếm ký tự (WV-15), lỗi hiện thông điệp của server, nội dung đã xoá.
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { ENVELOPE, SESSION, message, summary } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import { ChatPage } from './ChatPage'
import { MAX_TURN_CHARS } from './turnStream'

const messagesUrl = `/api/v1/chat-sessions/${SESSION.id}/messages`
const turnUrl = `/api/v1/chat-sessions/${SESSION.id}/turns`
const open = http.post('/api/v1/chat-sessions', () => HttpResponse.json(SESSION, { status: 201 }))
const sse = (...events: [string, unknown][]) => new HttpResponse(events.map(([e, d]) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`).join(''), { headers: { 'Content-Type': 'text/event-stream' } })
const view = () => renderWithProviders(<ChatPage />)

describe('ChatPage', () => {
  it('mở phiên với Idempotency-Key và hiện lịch sử từ cũ tới mới (API trả giảm dần)', async () => {
    let key: string | null = null
    server.use(
      http.post('/api/v1/chat-sessions', ({ request }) => {
        key = request.headers.get('Idempotency-Key')
        return HttpResponse.json(SESSION, { status: 201 })
      }),
      http.get(messagesUrl, () => HttpResponse.json({ items: [message(2, 'AGENT', 'Câu trả lời'), message(1, 'EMPLOYEE', 'Câu hỏi')], next_cursor: null })),
    )
    view()
    const items = await screen.findAllByRole('listitem')
    expect(items.map((li) => li.textContent)).toEqual(['BạnCâu hỏi', 'Trợ lýCâu trả lời'])
    expect(key).toMatch(/^[0-9a-f-]{36}$/)
  })

  it('phiên trống → gợi ý; nút Gửi bị khoá khi chưa gõ', async () => {
    server.use(open, http.get(messagesUrl, () => HttpResponse.json({ items: [], next_cursor: null })))
    view()
    expect(await screen.findByText(/Hãy nói điều bạn cần/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Gửi' })).toBeDisabled()
  })

  it('gửi một lượt: hiện tin của bạn, tiến trình, câu trả lời và liên kết tới yêu cầu đang xử lý', async () => {
    const mine = message(1, 'EMPLOYEE', 'Tôi cần giấy xác nhận công tác')
    const reply = message(2, 'AGENT', 'Mình đã mở yêu cầu cho bạn.')
    let sent = false
    server.use(
      open,
      http.get(messagesUrl, () => HttpResponse.json({ items: sent ? [reply, mine] : [], next_cursor: null })),
      http.post(turnUrl, async ({ request }) => {
        expect(await request.json()).toEqual({ text: 'Tôi cần giấy xác nhận công tác' })
        expect(request.headers.get('Idempotency-Key')).toMatch(/^[0-9a-f-]{36}$/)
        sent = true
        return sse(['turn.accepted', { message: mine }], ['turn.progress', { stage: 'UNDERSTANDING' }], ['turn.reply', { message: reply, active_request: summary(), pending_question: null }])
      }),
    )
    view()
    await userEvent.type(await screen.findByLabelText('Tin nhắn'), 'Tôi cần giấy xác nhận công tác')
    await userEvent.click(screen.getByRole('button', { name: 'Gửi' }))
    expect(await screen.findByText('Mình đã mở yêu cầu cho bạn.')).toBeInTheDocument()
    expect(screen.getByText('Tôi cần giấy xác nhận công tác')).toBeInTheDocument()
    const link = await screen.findByRole('link', { name: 'Giấy xác nhận công tác' })
    expect(link).toHaveAttribute('href', `/my-requests/${summary().id}`)
    expect(screen.getByLabelText('Tin nhắn')).toHaveValue('')
  })

  it('Enter gửi, Shift+Enter xuống dòng', async () => {
    let posts = 0
    server.use(
      open,
      http.get(messagesUrl, () => HttpResponse.json({ items: [], next_cursor: null })),
      http.post(turnUrl, () => {
        posts++
        return sse(['turn.reply', { message: message(2, 'AGENT', 'ok'), active_request: null, pending_question: null }])
      }),
    )
    view()
    const box = await screen.findByLabelText('Tin nhắn')
    await userEvent.type(box, 'dòng 1{Shift>}{Enter}{/Shift}dòng 2')
    expect(box).toHaveValue('dòng 1\ndòng 2')
    await userEvent.type(box, '{Enter}')
    await waitFor(() => expect(posts).toBe(1))
  })

  it(`đếm ký tự và khoá gửi khi vượt ${MAX_TURN_CHARS}`, async () => {
    server.use(open, http.get(messagesUrl, () => HttpResponse.json({ items: [], next_cursor: null })))
    view()
    const box = await screen.findByLabelText('Tin nhắn')
    await userEvent.click(box)
    await userEvent.paste('a'.repeat(MAX_TURN_CHARS))
    expect(screen.getByText(`${MAX_TURN_CHARS}/${MAX_TURN_CHARS} ký tự`)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Gửi' })).toBeEnabled()
    await userEvent.paste('b')
    expect(screen.getByText(/tin nhắn quá dài/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Gửi' })).toBeDisabled()
  })

  it('lỗi trước stream (TURN_IN_PROGRESS) hiện nguyên thông điệp của server và trả lại nội dung đã gõ', async () => {
    server.use(
      open,
      http.get(messagesUrl, () => HttpResponse.json({ items: [], next_cursor: null })),
      http.post(turnUrl, () => HttpResponse.json(ENVELOPE('TURN_IN_PROGRESS', 'Lượt trước của bạn chưa xong, vui lòng chờ.'), { status: 409 })),
    )
    view()
    const box = await screen.findByLabelText('Tin nhắn')
    await userEvent.type(box, 'xin chào')
    await userEvent.click(screen.getByRole('button', { name: 'Gửi' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Lượt trước của bạn chưa xong, vui lòng chờ.')
    await waitFor(() => expect(box).toHaveValue('xin chào'))
  })

  it('nội dung đã xoá hiện "nội dung đã xoá", không phải null', async () => {
    server.use(open, http.get(messagesUrl, () => HttpResponse.json({ items: [{ ...message(1, 'EMPLOYEE', 'x'), body: null, content_erased: true }], next_cursor: null })))
    view()
    expect(await screen.findByText('nội dung đã xoá')).toBeInTheDocument()
  })

  it('phân trang: "Tải tin cũ hơn" gọi trang kế bằng cursor', async () => {
    const cursors: (string | null)[] = []
    server.use(
      open,
      http.get(messagesUrl, ({ request }) => {
        const cursor = new URL(request.url).searchParams.get('cursor')
        cursors.push(cursor)
        return cursor ? HttpResponse.json({ items: [message(1, 'EMPLOYEE', 'cũ')], next_cursor: null }) : HttpResponse.json({ items: [message(2, 'AGENT', 'mới')], next_cursor: 'c1' })
      }),
    )
    view()
    await userEvent.click(await screen.findByRole('button', { name: 'Tải tin cũ hơn' }))
    await screen.findByText('cũ')
    expect(cursors).toEqual([null, 'c1'])
    expect((await screen.findAllByRole('listitem')).map((li) => li.textContent)).toEqual(['Bạncũ', 'Trợ lýmới'])
  })

  it('mở phiên lỗi → thông điệp của server', async () => {
    server.use(http.post('/api/v1/chat-sessions', () => HttpResponse.json(ENVELOPE('PERMISSION_DENIED', 'Bạn không có quyền trò chuyện.'), { status: 403 })))
    view()
    expect(await screen.findByRole('alert')).toHaveTextContent('Bạn không có quyền trò chuyện.')
  })
})
