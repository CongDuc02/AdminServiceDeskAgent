// Stream lượt chat — NGOÀI TanStack Query (ADR-018; 05-api.md mục 3.1). Ngoại lệ DUY NHẤT của luật "features không import api/transport": file này được import `http` và `sse`.
//
// Một lượt = một `POST /chat-sessions/{id}/turns` với `Idempotency-Key` = id tin nhắn của nhân viên, đọc `turn.accepted` → `turn.progress`* → `turn.reply` | `turn.error`.
// Bản có thẩm quyền là dòng `chat_message`, không phải stream. LUẬT DỰNG LẠI khi stream đứt trước `turn.reply`/`turn.error` (ADR-018):
//   1. GET /chat-sessions/{id}/messages;
//   2. tin nhắn agent của lượt đã có → hiển thị nó, xong;
//   3. chưa có → gửi lại CÙNG Idempotency-Key. Server trả 409 `TURN_NOT_FINISHED`: `turn_abandoned = false` → chờ theo `Retry-After` rồi quay lại bước 1;
//      `turn_abandoned = true` → hiển thị đúng `message` của server (tin nhắn đã được lưu, cần gửi lại nội dung).
// Tin agent của lượt được nhận ra bằng thứ tự: tin AGENT có `seq` nhỏ nhất lớn hơn `seq` tin nhân viên và không có tin nhân viên nào chen giữa (ChatMessage không mang `in_reply_to`).
import { listChatMessages, type ChatMessage, type TurnReply, type TurnStage } from '@/api/endpoints/chat'
import { ApiError, postStream, type ErrorEnvelope } from '@/api/transport/http'
import { parseSse } from '@/api/transport/sse'

/** WV-15: trần số ký tự mỗi tin nhắn (server kiểm; client chỉ đếm để báo trước). */
export const MAX_TURN_CHARS = 2000
const MAX_RECOVERY_ROUNDS = 12
const DEFAULT_WAIT_S = 2
const MAX_WAIT_S = 10

export type TurnEvent = { type: 'accepted'; message: ChatMessage } | { type: 'progress'; stage: TurnStage }

export type TurnOutcome =
  | { kind: 'reply'; reply: TurnReply } // đọc từ stream
  | { kind: 'recovered'; employee: ChatMessage; agent: ChatMessage } // dựng lại từ GET messages
  | { kind: 'abandoned'; error: ApiError } // TURN_NOT_FINISHED, turn_abandoned = true: tin đã lưu nhưng hệ thống không trả lời được
  | { kind: 'gave_up' } // hết số vòng dựng lại mà lượt vẫn chưa xong: để người dùng tải lại

export type SendTurnOptions = {
  sessionId: string
  text: string
  /** id tin nhắn của nhân viên = Idempotency-Key. Người gọi giữ ổn định cho cả lượt, kể cả khi gửi lại. */
  messageId: string
  onEvent?: (event: TurnEvent) => void
  signal?: AbortSignal
  /** Tiêm được để test không phải chờ thật. */
  sleep?: (seconds: number) => Promise<void>
}

type Step =
  | { type: 'reply'; reply: TurnReply }
  | { type: 'broken' } // stream đứt, hoặc mất mạng: chưa biết server đã nhận tin chưa
  | { type: 'wait'; seconds: number }
  | { type: 'abandoned'; error: ApiError }

const realSleep = (seconds: number) => new Promise<void>((resolve) => setTimeout(resolve, seconds * 1000))

function envelopeError(envelope: ErrorEnvelope): ApiError {
  return new ApiError(200, envelope.error_code, envelope.message, envelope, new Headers())
}

async function streamOnce(opts: SendTurnOptions): Promise<Step> {
  let response: Response
  try {
    response = await postStream(`/chat-sessions/${opts.sessionId}/turns`, { body: { text: opts.text }, headers: { 'Idempotency-Key': opts.messageId }, signal: opts.signal })
  } catch (e) {
    if (e instanceof ApiError) {
      if (e.code === 'CLIENT_NETWORK') return { type: 'broken' }
      if (e.code === 'TURN_NOT_FINISHED') {
        if (e.details.turn_abandoned === true) return { type: 'abandoned', error: e }
        return { type: 'wait', seconds: Math.min(MAX_WAIT_S, Math.max(1, e.retryAfterSeconds ?? DEFAULT_WAIT_S)) }
      }
    }
    throw e // lỗi trước khi stream bắt đầu (xác thực, quyền, phiên đã đóng, TURN_IN_PROGRESS, …): ErrorEnvelope của server, người gọi hiển thị
  }
  try {
    for await (const ev of parseSse(response.body!)) {
      const data = JSON.parse(ev.data) as unknown
      if (ev.event === 'turn.accepted') opts.onEvent?.({ type: 'accepted', message: (data as { message: ChatMessage }).message })
      else if (ev.event === 'turn.progress') opts.onEvent?.({ type: 'progress', stage: (data as { stage: TurnStage }).stage })
      else if (ev.event === 'turn.reply') return { type: 'reply', reply: data as TurnReply }
      else if (ev.event === 'turn.error') throw envelopeError(data as ErrorEnvelope)
    }
  } catch (e) {
    if (e instanceof ApiError) throw e // `turn.error` của server
    if (e instanceof DOMException && e.name === 'AbortError') throw e
    return { type: 'broken' } // đứt giữa chừng, hay một sự kiện hỏng
  }
  return { type: 'broken' } // luồng kết thúc mà không có `turn.reply` / `turn.error`
}

/** Tin agent của lượt có tin nhân viên `messageId`, nếu đã có trong danh sách (mới nhất trước). */
export function findTurnReply(messages: readonly ChatMessage[], messageId: string): { employee: ChatMessage; agent: ChatMessage } | null {
  const ascending = [...messages].sort((a, b) => a.seq - b.seq)
  const at = ascending.findIndex((m) => m.id === messageId)
  if (at === -1) return null
  const employee = ascending[at]!
  for (const m of ascending.slice(at + 1)) {
    if (m.author === 'EMPLOYEE') return null // đã có lượt sau mà lượt này không có tin agent: không đoán
    if (m.author === 'AGENT') return { employee, agent: m }
  }
  return null
}

export async function sendTurn(opts: SendTurnOptions): Promise<TurnOutcome> {
  const sleep = opts.sleep ?? realSleep
  let step = await streamOnce(opts)
  for (let round = 0; round < MAX_RECOVERY_ROUNDS; round++) {
    if (step.type === 'reply') return { kind: 'reply', reply: step.reply }
    if (step.type === 'abandoned') return { kind: 'abandoned', error: step.error }
    if (step.type === 'wait') await sleep(step.seconds)
    // 1–2. dựng lại từ dòng chat_message
    const page = await listChatMessages(opts.sessionId)
    const found = findTurnReply(page.items, opts.messageId)
    if (found) return { kind: 'recovered', ...found }
    // 3. chưa có: gửi lại cùng khoá
    step = await streamOnce(opts)
  }
  if (step.type === 'reply') return { kind: 'reply', reply: step.reply }
  if (step.type === 'abandoned') return { kind: 'abandoned', error: step.error }
  return { kind: 'gave_up' }
}
