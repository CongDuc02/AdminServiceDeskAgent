// Hook dữ liệu của tính năng chat: phiên, tin nhắn, và một lượt (`useTurn`). Component chỉ gọi hook (06-structure.md mục 10, "Hook").
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useMemo, useRef, useState } from 'react'
import { listChatMessages, openChatSession, type ChatMessage, type PendingQuestion, type TurnStage } from '@/api/endpoints/chat'
import type { RequestSummary } from '@/api/endpoints/requests'
import { ROOT_MY_REQUESTS, queryKeys } from '@/api/queryKeys'
import { sendTurn, type TurnOutcome } from '@/features/chat/turnStream'

export function useChatSession() {
  // Một khoá mở phiên cho cả vòng đời trang: mở lại cùng khoá trả lại cùng phiên (x-bo19-idempotency-key: chat_session).
  const [key] = useState(() => crypto.randomUUID())
  return useQuery({ queryKey: queryKeys.chat.session, queryFn: () => openChatSession(key), staleTime: Infinity, retry: false })
}

export function useChatMessages(sessionId: string | undefined) {
  const query = useInfiniteQuery({
    queryKey: queryKeys.chat.messages(sessionId ?? ''),
    enabled: !!sessionId,
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => listChatMessages(sessionId!, pageParam, 50),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  })
  // API trả `seq` giảm dần; màn hình đọc từ cũ tới mới.
  const messages = useMemo(() => {
    const byId = new Map<string, ChatMessage>()
    for (const page of query.data?.pages ?? []) for (const m of page.items) byId.set(m.id, m)
    return [...byId.values()].sort((a, b) => a.seq - b.seq)
  }, [query.data])
  return { ...query, messages }
}

export type TurnState = {
  sending: boolean
  stage: TurnStage | null
  /** Tin nhân viên vừa gửi, hiện ngay khi server xác nhận đã lưu (turn.accepted) — trước khi danh sách tin nhắn được làm mới. */
  pendingMessage: ChatMessage | null
  activeRequest: RequestSummary | null
  pendingQuestion: PendingQuestion | null
  /** Thông điệp của server khi lượt không trả lời được (tin đã lưu); null khi ổn. */
  notice: string | null
  error: unknown
}

const IDLE: TurnState = { sending: false, stage: null, pendingMessage: null, activeRequest: null, pendingQuestion: null, notice: null, error: null }

export function useTurn(sessionId: string | undefined) {
  const client = useQueryClient()
  const [state, setState] = useState<TurnState>(IDLE)
  const inFlight = useRef(false)

  const mutation = useMutation({
    mutationFn: async (text: string): Promise<TurnOutcome> => {
      return sendTurn({
        sessionId: sessionId!,
        text,
        messageId: crypto.randomUUID(),
        onEvent: (ev) => {
          if (ev.type === 'accepted') setState((s) => ({ ...s, pendingMessage: ev.message }))
          else setState((s) => ({ ...s, stage: ev.stage }))
        },
      })
    },
  })

  const send = useCallback(
    async (text: string): Promise<boolean> => {
      if (!sessionId || inFlight.current) return false
      inFlight.current = true
      setState({ ...IDLE, sending: true })
      try {
        const outcome = await mutation.mutateAsync(text)
        if (outcome.kind === 'reply') setState({ ...IDLE, activeRequest: outcome.reply.active_request, pendingQuestion: outcome.reply.pending_question })
        else if (outcome.kind === 'abandoned') setState({ ...IDLE, notice: outcome.error.message })
        else if (outcome.kind === 'gave_up') setState({ ...IDLE, notice: 'Hệ thống chưa trả lời xong. Tin nhắn của bạn đã được lưu — vui lòng tải lại trang để xem câu trả lời.' })
        else setState({ ...IDLE })
        return outcome.kind === 'reply' || outcome.kind === 'recovered'
      } catch (e) {
        setState({ ...IDLE, error: e })
        return false
      } finally {
        inFlight.current = false
        await client.invalidateQueries({ queryKey: queryKeys.chat.messages(sessionId) })
        await client.invalidateQueries({ queryKey: ROOT_MY_REQUESTS })
      }
    },
    [client, mutation, sessionId],
  )

  return { ...state, send }
}
