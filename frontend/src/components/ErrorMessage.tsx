// Hiển thị lỗi: `message` của server NGUYÊN VĂN (NFR-04) và mã truy vết để người dùng báo lại. Không nhận exception — nhận chuỗi đã rút ra ở nơi gọi.
import styles from '@/components/ui.module.css'

export function ErrorMessage({ message, traceId }: { message: string; traceId?: string | null }) {
  return (
    <div role="alert" className={styles.error}>
      {message}
      {traceId ? <span className={styles.errorTrace}>Mã truy vết: {traceId}</span> : null}
    </div>
  )
}
