// /my-requests/:requestId — chi tiết yêu cầu của người tạo: bảng slot (độ nhạy, nguồn gốc), xác nhận từng slot, thanh gửi, và các văn bản (số, tải bản FINAL).
// Nhãn trạng thái do server trả (`status_label`) — client không giữ bảng tên trạng thái (ADR-018). Rẽ nhánh lỗi theo `error_code`.
import { useState } from 'react'
import { useParams } from 'react-router-dom'
import type { DocumentOwnerView, RequestDetail, SlotView } from '@/api/endpoints/requests'
import { errorCode, traceIdOf, userMessage } from '@/api/errors'
import { DownloadButton } from '@/components/DownloadButton'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Loading } from '@/components/Loading'
import { ProvenanceTag } from '@/components/ProvenanceTag'
import { SensitiveValue } from '@/components/SensitiveValue'
import styles from '@/components/ui.module.css'
import { saveFinalPdf, useConfirmSlots, useRequestDetail, useSubmitRequest } from '@/features/my-requests/useMyRequests'

const EDITABLE = new Set(['DRAFT', 'NEEDS_INFO'])

function display(slot: SlotView): string | null {
  const v = slot.value
  if (v === null || v === undefined) return null
  return typeof v === 'string' ? v : JSON.stringify(v)
}

function labelOf(detail: RequestDetail, slotName: string): string {
  return detail.slots.find((s) => s.slot_name === slotName)?.label ?? slotName
}

function SlotRow({ slot, editable, busy, onConfirm }: { slot: SlotView; editable: boolean; busy: boolean; onConfirm: (s: SlotView) => void }) {
  const proposed = slot.value_status === 'PROPOSED' && slot.row_version !== null
  return (
    <tr>
      <th scope="row" style={{ textAlign: 'left', verticalAlign: 'top', padding: '0.4rem 0.5rem 0.4rem 0' }}>
        {slot.label}
        {slot.is_required ? <span aria-label="bắt buộc"> *</span> : null}
      </th>
      <td style={{ padding: '0.4rem 0.5rem' }}>
        <SensitiveValue value={display(slot)} sensitivity={slot.sensitivity} erased={slot.erased} />
        {slot.provenance ? (
          <div>
            <ProvenanceTag source={slot.provenance.source} syncedAt={slot.provenance.synced_at} />
          </div>
        ) : null}
      </td>
      <td style={{ padding: '0.4rem 0' }}>
        {slot.value_status === 'CONFIRMED' ? <span className={styles.badge}>Đã xác nhận</span> : null}
        {proposed ? (
          <>
            <span className={`${styles.badge} ${styles.badgeWarn}`}>Chờ bạn xác nhận</span>{' '}
            {editable ? (
              <button type="button" className={`${styles.button} ${styles.buttonSecondary}`} disabled={busy} onClick={() => onConfirm(slot)}>
                Xác nhận
              </button>
            ) : null}
          </>
        ) : null}
      </td>
    </tr>
  )
}

function DocumentRow({ doc }: { doc: DocumentOwnerView }) {
  const [error, setError] = useState<unknown>(null)
  return (
    <li style={{ margin: '0.5rem 0' }}>
      <strong>{doc.status_label}</strong>
      {doc.document_number ? <span> — Số: {doc.document_number}</span> : null}
      {doc.issued_date ? <span> — Ngày: {new Date(doc.issued_date).toLocaleDateString('vi-VN')}</span> : null}
      {doc.final_render_id ? (
        <div style={{ marginTop: '0.4rem' }}>
          <DownloadButton
            label="Tải bản PDF"
            onDownload={async () => {
              setError(null)
              try {
                await saveFinalPdf(doc.id, doc.final_render_id!, doc.document_number ? `giay-xac-nhan-${doc.document_number.replace(/[^\w.-]+/g, '-')}` : `van-ban-${doc.id}`)
              } catch (e) {
                setError(e)
              }
            }}
          />
        </div>
      ) : null}
      {error ? <ErrorMessage message={userMessage(error)} traceId={traceIdOf(error)} /> : null}
    </li>
  )
}

export function RequestDetailPage() {
  const { requestId = '' } = useParams()
  const detail = useRequestDetail(requestId)
  const confirm = useConfirmSlots(requestId)
  const submit = useSubmitRequest(requestId)

  if (detail.isPending) return <Loading />
  if (detail.isError) {
    return errorCode(detail.error) === 'NOT_FOUND' ? <ErrorMessage message={userMessage(detail.error)} /> : <ErrorMessage message={userMessage(detail.error)} traceId={traceIdOf(detail.error)} />
  }
  const r = detail.data
  const editable = EDITABLE.has(r.status)
  const proposed = r.slots.filter((s) => s.value_status === 'PROPOSED' && s.row_version !== null)
  const blockers = [
    ...r.missing_slots.map((n) => `Còn thiếu: ${labelOf(r, n)}`),
    ...r.unconfirmed_slots.map((n) => `Chưa xác nhận: ${labelOf(r, n)}`),
    ...r.failed_rules.map((f) => `Chưa đạt kiểm tra: ${labelOf(r, f.slot_name)}`),
  ]
  const confirmOne = (s: SlotView) => confirm.mutate([{ slot_name: s.slot_name, expected_row_version: s.row_version! }])
  const confirmAll = () => confirm.mutate(proposed.map((s) => ({ slot_name: s.slot_name, expected_row_version: s.row_version! })))

  return (
    <main style={{ maxWidth: 760, margin: '0 auto', padding: '1rem' }}>
      <h1>
        {r.request_type_name}
        <span className={styles.badge}>{r.status_label}</span>
      </h1>
      <p className={styles.muted}>Tạo lúc {new Date(r.created_at).toLocaleString('vi-VN')}</p>

      <h2>Thông tin</h2>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <tbody>
          {r.slots.map((s) => (
            <SlotRow key={s.slot_name} slot={s} editable={editable} busy={confirm.isPending} onConfirm={confirmOne} />
          ))}
        </tbody>
      </table>
      {editable && proposed.length > 1 ? (
        <p>
          <button type="button" className={styles.button} disabled={confirm.isPending} onClick={confirmAll}>
            Xác nhận tất cả đề xuất
          </button>
        </p>
      ) : null}
      {confirm.isError ? <ErrorMessage message={userMessage(confirm.error)} traceId={traceIdOf(confirm.error)} /> : null}

      {editable ? (
        <section aria-label="Gửi yêu cầu">
          <h2>Gửi yêu cầu</h2>
          {blockers.length > 0 ? (
            <ul>
              {blockers.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          ) : null}
          <button type="button" className={styles.button} disabled={!r.submit_ready || submit.isPending} onClick={() => submit.mutate(r.row_version)}>
            {submit.isPending ? 'Đang gửi…' : 'Gửi yêu cầu'}
          </button>
          {submit.isError ? <ErrorMessage message={userMessage(submit.error)} traceId={traceIdOf(submit.error)} /> : null}
        </section>
      ) : null}

      {r.documents.length > 0 ? (
        <section aria-label="Văn bản">
          <h2>Văn bản</h2>
          <ul style={{ listStyle: 'none', padding: 0 }}>
            {r.documents.map((d) => (
              <DocumentRow key={d.id} doc={d} />
            ))}
          </ul>
        </section>
      ) : null}
    </main>
  )
}
