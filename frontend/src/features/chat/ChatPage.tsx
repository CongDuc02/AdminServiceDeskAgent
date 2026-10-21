// /chat — hội thoại với agent (F1). Mỗi lượt: gửi, thấy tiến trình, thấy câu trả lời; stream đứt thì dựng lại từ dòng chat_message (turnStream.ts). Nhãn trạng thái do server trả.
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { Link } from 'react-router-dom'
import type { TurnStage } from '@/api/endpoints/chat'
import { traceIdOf, userMessage } from '@/api/errors'
import { EmptyState } from '@/components/EmptyState'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Loading } from '@/components/Loading'
import styles from '@/components/ui.module.css'
import { MAX_TURN_CHARS } from '@/features/chat/turnStream'
import { useChatMessages, useChatSession, useTurn } from '@/features/chat/useChat'

// Chữ hiển thị của ba giai đoạn (`stage` không phải tên node — 05-api.md mục 3.1).
const STAGE_LABEL: Record<TurnStage, string> = {
  UNDERSTANDING: 'Đang hiểu yêu cầu…',
  LOOKING_UP: 'Đang tra cứu quy trình…',
  PREPARING_REPLY: 'Đang soạn câu trả lời…',
}

export function ChatPage() {
  const session = useChatSession()
  const sessionId = session.data?.id
  const history = useChatMessages(sessionId)
  const turn = useTurn(sessionId)
  const [text, setText] = useState('')
  const endRef = useRef<HTMLDivElement | null>(null)

  const shown = history.messages
  const pending = turn.pendingMessage && !shown.some((m) => m.id === turn.pendingMessage!.id) ? turn.pendingMessage : null

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: 'end' })
  }, [shown.length, pending, turn.stage])

  if (session.isPending) return <Loading label="Đang mở phiên trò chuyện…" />
  if (session.isError) return <ErrorMessage message={userMessage(session.error)} traceId={traceIdOf(session.error)} />

  const tooLong = text.length > MAX_TURN_CHARS
  const canSend = !turn.sending && text.trim() !== '' && !tooLong

  const submit = async (e?: FormEvent) => {
    e?.preventDefault()
    if (!canSend) return
    const sent = text
    setText('')
    const ok = await turn.send(sent)
    if (!ok) setText((cur) => (cur === '' ? sent : cur)) // lượt hỏng: trả lại nội dung để gửi lại
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      void submit()
    }
  }

  return (
    <main style={{ maxWidth: 760, margin: '0 auto', padding: '1rem' }}>
      <h1>Trò chuyện</h1>
      {history.hasNextPage ? (
        <p>
          <button type="button" className={`${styles.button} ${styles.buttonSecondary}`} onClick={() => void history.fetchNextPage()} disabled={history.isFetchingNextPage}>
            Tải tin cũ hơn
          </button>
        </p>
      ) : null}
      <section aria-label="Danh sách tin nhắn" style={{ minHeight: 240 }}>
        {history.isPending ? <Loading /> : null}
        {history.isError ? <ErrorMessage message={userMessage(history.error)} traceId={traceIdOf(history.error)} /> : null}
        {!history.isPending && shown.length === 0 && !pending ? <EmptyState>Hãy nói điều bạn cần, ví dụ: “Tôi cần giấy xác nhận công tác”.</EmptyState> : null}
        <ul style={{ listStyle: 'none', padding: 0 }}>
          {[...shown, ...(pending ? [pending] : [])].map((m) => (
            <li key={m.id} style={{ margin: '0.5rem 0', textAlign: m.author === 'EMPLOYEE' ? 'right' : 'left' }}>
              <span className={styles.muted}>{m.author === 'EMPLOYEE' ? 'Bạn' : 'Trợ lý'}</span>
              <div style={{ whiteSpace: 'pre-wrap' }}>{m.content_erased ? <em>nội dung đã xoá</em> : m.body}</div>
            </li>
          ))}
        </ul>
        {turn.sending && turn.stage ? (
          <p role="status" className={styles.muted}>
            {STAGE_LABEL[turn.stage]}
          </p>
        ) : null}
        {turn.sending && !turn.stage ? (
          <p role="status" className={styles.muted}>
            Đang gửi…
          </p>
        ) : null}
        <div ref={endRef} />
      </section>

      {turn.notice ? <ErrorMessage message={turn.notice} /> : null}
      {turn.error ? <ErrorMessage message={userMessage(turn.error)} traceId={traceIdOf(turn.error)} /> : null}
      {turn.activeRequest ? (
        <p>
          Yêu cầu đang xử lý: <Link to={`/my-requests/${turn.activeRequest.id}`}>{turn.activeRequest.request_type_name}</Link> — {turn.activeRequest.status_label}
        </p>
      ) : null}

      <form onSubmit={submit}>
        <label htmlFor="turn-text" className={styles.muted}>
          Tin nhắn
        </label>
        <textarea
          id="turn-text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          rows={3}
          style={{ width: '100%', boxSizing: 'border-box' }}
          aria-describedby="turn-count"
          disabled={turn.sending}
        />
        <p id="turn-count" className={styles.muted} style={tooLong ? { color: '#c0392b' } : undefined}>
          {text.length}/{MAX_TURN_CHARS} ký tự{tooLong ? ' — tin nhắn quá dài, hãy rút gọn' : ''}
        </p>
        <button type="submit" className={styles.button} disabled={!canSend}>
          Gửi
        </button>
      </form>
    </main>
  )
}
