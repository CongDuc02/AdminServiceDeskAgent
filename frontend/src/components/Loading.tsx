import styles from '@/components/ui.module.css'

export function Loading({ label = 'Đang tải…' }: { label?: string }) {
  return (
    <p role="status" className={styles.loading}>
      {label}
    </p>
  )
}
