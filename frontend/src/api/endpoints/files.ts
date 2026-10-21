// Tải bản render — mục Tải file của 05-api.md (`downloadRender`). Người tạo (`request.read_own`) chỉ tải được bản FINAL, chỉ pdf, chỉ sau ISSUED; server kiểm.
import { getBlob } from '@/api/transport/http'

export type DownloadedFile = { blob: Blob; contentType: string; contentDisposition: string | null }

export function downloadRender(documentId: string, renderId: string, format: 'pdf' | 'docx' = 'pdf'): Promise<DownloadedFile> {
  return getBlob(`/documents/${documentId}/renders/${renderId}/file`, { query: { format } })
}
