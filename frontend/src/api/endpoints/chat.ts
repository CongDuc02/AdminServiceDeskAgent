// Nhóm endpoint chat — mục Chat của 05-api.md. Stream lượt (POST …/turns) nằm ở features/chat/turnStream.ts (ngoại lệ duy nhất của luật transport).
import type { components } from '@/api/generated/openapi'
import { request, get } from '@/api/transport/http'

export type ChatSession = components['schemas']['ChatSession']
export type ChatMessage = components['schemas']['ChatMessage']
export type ChatMessagePage = components['schemas']['ChatMessagePage']
export type TurnReply = components['schemas']['TurnReplyEvent']
export type PendingQuestion = components['schemas']['PendingQuestionView']
export type TurnStage = components['schemas']['TurnProgressEvent']['stage']

/** Lấy phiên đang mở hoặc mở phiên mới. `Idempotency-Key` do người gọi giữ ổn định cho một lần mở. */
export async function openChatSession(idempotencyKey: string): Promise<ChatSession> {
  return (await request<ChatSession>('POST', '/chat-sessions', { headers: { 'Idempotency-Key': idempotencyKey } })).data
}

/** Tin nhắn của phiên, `seq` giảm dần (mới nhất trước). */
export function listChatMessages(sessionId: string, cursor?: string | null, limit?: number): Promise<ChatMessagePage> {
  return get<ChatMessagePage>(`/chat-sessions/${sessionId}/messages`, { query: { cursor: cursor ?? undefined, limit } })
}
