// Khoá gốc theo chủ đề tín hiệu (ADR-018): ba chủ đề, ba khoá gốc. Query nằm dưới khoá gốc của chủ đề nó thuộc về; query không thuộc chủ đề nào có khoá riêng.
// Sprint 3 (`GET /signals`) invalidate theo tiền tố những khoá gốc này.
export const ROOT_NOTIFICATIONS = ['notifications'] as const
export const ROOT_MY_REQUESTS = ['my-requests'] as const
export const ROOT_REVIEW_QUEUE = ['review-queue'] as const

export const queryKeys = {
  me: ['me'] as const,
  myRequests: {
    list: () => [...ROOT_MY_REQUESTS, 'list'] as const,
    detail: (requestId: string) => [...ROOT_MY_REQUESTS, 'detail', requestId] as const,
  },
  chat: {
    session: ['chat', 'session'] as const,
    messages: (sessionId: string) => ['chat', 'messages', sessionId] as const,
  },
}
