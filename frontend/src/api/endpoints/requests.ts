// Nhóm endpoint yêu cầu của người tạo — mục Yêu cầu của 05-api.md (Sprint 1: scope=OWN, confirm-slots, submit).
import type { components } from '@/api/generated/openapi'
import { get, post } from '@/api/transport/http'

export type RequestSummary = components['schemas']['RequestSummary']
export type RequestSummaryPage = components['schemas']['RequestSummaryPage']
export type RequestDetail = components['schemas']['RequestDetail']
export type SlotView = components['schemas']['SlotView']
export type DecisionResult = components['schemas']['DecisionResult']
export type DocumentOwnerView = components['schemas']['DocumentOwnerView']
export type SlotConfirmation = { slot_name: string; expected_row_version: number }

export function listMyRequests(cursor?: string | null, limit?: number): Promise<RequestSummaryPage> {
  return get<RequestSummaryPage>('/requests', { query: { scope: 'OWN', cursor: cursor ?? undefined, limit } })
}

export function getRequest(requestId: string): Promise<RequestDetail> {
  return get<RequestDetail>(`/requests/${requestId}`)
}

export function confirmSlots(requestId: string, confirmations: SlotConfirmation[]): Promise<RequestDetail> {
  return post<RequestDetail>(`/requests/${requestId}/actions/confirm-slots`, { body: { confirmations } })
}

/** `Idempotency-Key` = id của `decision_record` sẽ ghi (05-api.md); người gọi giữ ổn định giữa các lần thử lại của cùng một thao tác. */
export function submitRequest(requestId: string, expectedRowVersion: number, idempotencyKey: string): Promise<DecisionResult> {
  return post<DecisionResult>(`/requests/${requestId}/actions/submit`, { body: { expected_row_version: expectedRowVersion }, headers: { 'Idempotency-Key': idempotencyKey } })
}
