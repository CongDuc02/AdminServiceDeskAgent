// Nguồn của giá trị `HR_PROFILE` (D-002 ràng buộc 3): tên nguồn và thời điểm đồng bộ. Giờ hiện theo múi giờ của trình duyệt.
import styles from '@/components/ui.module.css'

export function ProvenanceTag({ source, syncedAt }: { source: string; syncedAt: string }) {
  const when = new Date(syncedAt)
  const text = Number.isNaN(when.getTime()) ? syncedAt : when.toLocaleString('vi-VN')
  return (
    <span className={styles.muted}>
      Nguồn: {source}, đồng bộ {text}
    </span>
  )
}
