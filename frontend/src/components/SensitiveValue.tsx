// Giá trị slot kèm độ nhạy (INT · PER · RES). Giá trị đã xoá hiện "nội dung đã xoá" (A-014). KHÔNG ghi giá trị ra console, storage hay thuộc tính `title`.
import styles from '@/components/ui.module.css'

export type Sensitivity = 'INT' | 'PER' | 'RES'

const LABEL: Record<Sensitivity, string | null> = { INT: null, PER: 'Dữ liệu cá nhân', RES: 'Dữ liệu hạn chế' }

export function SensitiveValue({ value, sensitivity, erased }: { value: string | null; sensitivity: Sensitivity; erased: boolean }) {
  if (erased) return <em>nội dung đã xoá</em>
  const label = LABEL[sensitivity]
  return (
    <>
      {value === null || value === '' ? <span className={styles.muted}>(chưa có)</span> : <span>{value}</span>}
      {label ? <span className={`${styles.badge} ${sensitivity === 'RES' ? styles.badgeWarn : ''}`}>{label}</span> : null}
    </>
  )
}
