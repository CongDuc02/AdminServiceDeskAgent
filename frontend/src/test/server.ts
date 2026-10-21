// Máy chủ giả MSW chặn ở tầng mạng: lối `fetch` duy nhất (api/transport/http.ts) vẫn là đối tượng được kiểm, không bị mock (ADR-042).
import { setupServer } from 'msw/node'

export const server = setupServer()
