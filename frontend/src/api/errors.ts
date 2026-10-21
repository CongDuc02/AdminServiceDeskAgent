// Rẽ nhánh lỗi theo `error_code`, KHÔNG BAO GIỜ theo `message` (ADR-018); hiển thị `message` của server nguyên văn (NFR-04).
import { ApiError } from '@/api/transport/http'

export { ApiError }

export function isApiError(e: unknown): e is ApiError {
  return e instanceof ApiError
}

export function errorCode(e: unknown): string | null {
  return e instanceof ApiError ? e.code : null
}

/** Thông điệp để hiện cho người dùng: nguyên văn `message` của server (hoặc câu cố định của client khi không có envelope). */
export function userMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message
  return 'Đã xảy ra lỗi không xác định. Vui lòng thử lại.'
}

export function traceIdOf(e: unknown): string | null {
  return e instanceof ApiError ? e.traceId : null
}
