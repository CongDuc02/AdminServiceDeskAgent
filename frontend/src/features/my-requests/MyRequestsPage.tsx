// /my-requests — danh sách yêu cầu của chính mình (scope=OWN), chờ lâu nhất / mới nhất theo server; `status_label` do server trả.
import { Link } from 'react-router-dom'
import { traceIdOf, userMessage } from '@/api/errors'
import { EmptyState } from '@/components/EmptyState'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Loading } from '@/components/Loading'
import styles from '@/components/ui.module.css'
import { useMyRequests } from '@/features/my-requests/useMyRequests'

export function MyRequestsPage() {
  const list = useMyRequests()
  return (
    <main style={{ maxWidth: 760, margin: '0 auto', padding: '1rem' }}>
      <h1>Yêu cầu của tôi</h1>
      {list.isPending ? <Loading /> : null}
      {list.isError ? <ErrorMessage message={userMessage(list.error)} traceId={traceIdOf(list.error)} /> : null}
      {list.isSuccess && list.items.length === 0 ? <EmptyState>Bạn chưa có yêu cầu nào. Hãy bắt đầu ở mục Trò chuyện.</EmptyState> : null}
      <ul style={{ listStyle: 'none', padding: 0 }}>
        {list.items.map((r) => (
          <li key={r.id} style={{ borderBottom: '1px solid #eee', padding: '0.6rem 0' }}>
            <Link to={`/my-requests/${r.id}`}>{r.request_type_name}</Link>
            <span className={styles.badge}>{r.status_label}</span>
            <div className={styles.muted}>Cập nhật {new Date(r.status_changed_at).toLocaleString('vi-VN')}</div>
          </li>
        ))}
      </ul>
      {list.hasNextPage ? (
        <button type="button" className={`${styles.button} ${styles.buttonSecondary}`} onClick={() => void list.fetchNextPage()} disabled={list.isFetchingNextPage}>
          Tải thêm
        </button>
      ) : null}
    </main>
  )
}
