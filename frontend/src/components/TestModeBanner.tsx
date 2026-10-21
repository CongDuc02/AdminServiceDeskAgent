// Dải báo chế độ thử nghiệm: `Me.operating_mode = NON_PRODUCTION` thì mọi trang hiện dải này (06-structure.md mục 11). Watermark thật nằm trong bản render, không ở giao diện (NFR-03).
import styles from '@/components/ui.module.css'

export function TestModeBanner({ mode }: { mode: string }) {
  if (mode !== 'NON_PRODUCTION') return null
  return (
    <div role="note" className={styles.banner}>
      Chế độ thử nghiệm — dữ liệu là dữ liệu giả, văn bản không có giá trị pháp lý.
    </div>
  )
}
