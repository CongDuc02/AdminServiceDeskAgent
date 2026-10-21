// Dữ liệu GIẢ của test (A-080). Hình dạng theo contracts/openapi.yaml qua type sinh.
import type { components } from '@/api/generated/openapi'

type S = components['schemas']

export const ME: S['Me'] = {
  employee: { id: '11111111-1111-4111-8111-111111111111', employee_code: 'GIA-0001', full_name: 'NHÂN VIÊN GIẢ 01 (GIẢ)', department_code: 'GIA-PB', department_name: 'Phòng giả', job_title: 'Chức danh giả' },
  permissions: ['request.create', 'request.read_own'] as unknown as S['Me']['permissions'],
  operating_mode: 'NON_PRODUCTION',
}

export const ENVELOPE = (error_code: string, message: string, details?: S['ErrorEnvelope']['details']): S['ErrorEnvelope'] =>
  ({ error_code, message, trace_id: '123e4567-e89b-42d3-a456-426614174000', ...(details ? { details } : {}) }) as S['ErrorEnvelope']

export const SESSION: S['ChatSession'] = { id: '22222222-2222-4222-8222-222222222222', status: 'OPEN', opened_at: '2026-10-21T01:00:00Z', last_message_at: '2026-10-21T01:00:00Z', closed_at: null, close_reason: null }

export const message = (seq: number, author: 'EMPLOYEE' | 'AGENT', body: string, id = `00000000-0000-4000-8000-${String(seq).padStart(12, '0')}`): S['ChatMessage'] => ({
  id, seq, author, request_id: null, body, content_erased: false, reply_template_id: null, created_at: '2026-10-21T01:00:00Z',
})

export const REQUEST_ID = '33333333-3333-4333-8333-333333333333'
export const DOC_ID = '44444444-4444-4444-8444-444444444444'
export const RENDER_ID = '55555555-5555-4555-8555-555555555555'

export const summary = (over: Partial<S['RequestSummary']> = {}): S['RequestSummary'] => ({
  id: REQUEST_ID, request_type_code: 'WORK_CONFIRMATION' as S['RequestSummary']['request_type_code'], request_type_name: 'Giấy xác nhận công tác', status: 'DRAFT', status_label: 'Đang soạn',
  status_changed_at: '2026-10-21T01:00:00Z', created_at: '2026-10-21T01:00:00Z', created_by_employee_id: ME.employee.id, beneficiary: ME.employee, row_version: 3, artifacts: [], ...over,
})

export const slot = (over: Partial<S['SlotView']>): S['SlotView'] => ({
  slot_name: 'full_name' as S['SlotView']['slot_name'], label: 'Họ và tên', description: '', data_type: 'STRING', source: 'HR_PROFILE', sensitivity: 'PER', is_required: true,
  value: 'NGUYỄN VĂN A (GIẢ)', value_status: 'CONFIRMED', erased: false, provenance: { source: 'TEST_FAKE', synced_at: '2026-10-20T01:00:00Z' } as S['SlotView']['provenance'],
  proposed_from_request_id: null, confirmed_at: '2026-10-21T01:00:00Z', row_version: 2, ...over,
})

export const detail = (over: Partial<S['RequestDetail']> = {}): S['RequestDetail'] => ({
  ...summary(), slots: [slot({})], missing_slots: [], unconfirmed_slots: [], failed_rules: [], submit_ready: true, changes_requested: null, documents: [], ...over,
}) as S['RequestDetail']
