// Hook dữ liệu của "Yêu cầu của tôi": danh sách (scope=OWN), chi tiết, xác nhận slot, gửi. Khoá nằm dưới khoá gốc `['my-requests']` (ADR-018).
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useRef } from 'react'
import { downloadRender } from '@/api/endpoints/files'
import { confirmSlots, getRequest, listMyRequests, submitRequest, type RequestDetail, type RequestSummary, type SlotConfirmation } from '@/api/endpoints/requests'
import { ROOT_MY_REQUESTS, queryKeys } from '@/api/queryKeys'

// Chu kỳ làm mới tạm thời tới khi có `GET /signals` (Sprint 3) — ADR-018, mục Cập nhật 2026-10-21.
export const DETAIL_POLL_MS = 10_000

// `document` đã tới trạng thái cuối của thân văn bản: không còn gì để chờ.
const DOCUMENT_FINAL = new Set(['ISSUED', 'REVOKED', 'SUPERSEDED', 'ARCHIVED', 'REJECTED'])
// `request` đang chờ hệ thống hoặc cán bộ (không chờ chính người tạo): chỉ lúc đó polling mới có ích.
const REQUEST_WAITING = new Set(['SUBMITTED', 'IN_REVIEW', 'APPROVED'])

/** Có nên tự làm mới trang chi tiết không: `request` đang chờ hệ thống/cán bộ, hoặc còn `document` chưa ở trạng thái cuối. */
export function shouldPoll(detail: Pick<RequestDetail, 'status' | 'documents'> | undefined): boolean {
  if (!detail) return false
  if (REQUEST_WAITING.has(detail.status)) return true
  return detail.documents.some((d) => !DOCUMENT_FINAL.has(d.status))
}

export function useMyRequests() {
  const query = useInfiniteQuery({
    queryKey: queryKeys.myRequests.list(),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => listMyRequests(pageParam, 20),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  })
  const items = useMemo<RequestSummary[]>(() => query.data?.pages.flatMap((p) => p.items) ?? [], [query.data])
  return { ...query, items }
}

export function useRequestDetail(requestId: string) {
  return useQuery({
    queryKey: queryKeys.myRequests.detail(requestId),
    queryFn: () => getRequest(requestId),
    refetchOnWindowFocus: true,
    // Tạm thời tới `GET /signals`; dừng khi tab ẩn (`refetchIntervalInBackground` mặc định false).
    refetchInterval: (query) => (shouldPoll(query.state.data as RequestDetail | undefined) ? DETAIL_POLL_MS : false),
  })
}

export function useConfirmSlots(requestId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (confirmations: SlotConfirmation[]) => confirmSlots(requestId, confirmations),
    onSuccess: (detail) => client.setQueryData(queryKeys.myRequests.detail(requestId), detail),
    onError: () => client.invalidateQueries({ queryKey: queryKeys.myRequests.detail(requestId) }), // SLOT_VALUE_STALE & co.: lấy lại sự thật
  })
}

export function useSubmitRequest(requestId: string) {
  const client = useQueryClient()
  // Một khoá cho một ý định "gửi": bấm lại sau khi lỗi mạng dùng CÙNG khoá nên không ghi hai quyết định (05-api.md, Idempotency-Key = id decision_record).
  const key = useRef<string | null>(null)
  return useMutation({
    mutationFn: (expectedRowVersion: number) => {
      key.current ??= crypto.randomUUID()
      return submitRequest(requestId, expectedRowVersion, key.current)
    },
    onSuccess: () => {
      key.current = null
    },
    onError: (e) => {
      // Lỗi nghiệp vụ (409, 422…): lần bấm sau là ý định mới; mất mạng thì giữ khoá để lặp lại an toàn.
      if (!(e instanceof Error && 'code' in e && e.code === 'CLIENT_NETWORK')) key.current = null
    },
    onSettled: () => client.invalidateQueries({ queryKey: ROOT_MY_REQUESTS }),
  })
}

/** Tải bản FINAL qua lối `fetch` duy nhất rồi lưu tệp (ADR-042: lỗi hiện thông điệp của server, không phải trang JSON thô). */
export async function saveFinalPdf(documentId: string, renderId: string, fileStem: string): Promise<void> {
  const { blob } = await downloadRender(documentId, renderId, 'pdf')
  const href = URL.createObjectURL(blob)
  try {
    const a = document.createElement('a')
    a.href = href
    a.download = `${fileStem}.pdf`
    document.body.appendChild(a)
    a.click()
    a.remove()
  } finally {
    URL.revokeObjectURL(href)
  }
}
