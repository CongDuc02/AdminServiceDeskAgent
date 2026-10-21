// Nút tải tệp: nhận hàm tải (components không biết api). Lỗi do nơi gọi hiển thị bằng thông điệp của server.
import { useState } from 'react'
import styles from '@/components/ui.module.css'

export function DownloadButton({ label, onDownload }: { label: string; onDownload: () => Promise<void> }) {
  const [busy, setBusy] = useState(false)
  return (
    <button
      type="button"
      className={`${styles.button} ${styles.buttonSecondary}`}
      disabled={busy}
      onClick={async () => {
        setBusy(true)
        try {
          await onDownload()
        } finally {
          setBusy(false)
        }
      }}
    >
      {busy ? 'Đang tải…' : label}
    </button>
  )
}
