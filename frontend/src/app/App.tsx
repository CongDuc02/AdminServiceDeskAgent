// Gốc SPA: QueryClient, router, tuyến (06-structure.md mục 10.3). Đường dẫn SPA không bắt đầu bằng /api. Tuyến chỉ hiện khi người dùng có permission tương ứng — nhưng `api` mới là nơi kiểm.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useEffect, useMemo } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { setUnauthenticatedHandler } from '@/api/transport/http'
import { AuthGate } from '@/app/AuthGate'
import { Layout } from '@/app/Layout'
import { NotFoundPage } from '@/app/NotFoundPage'
import { LoginPage } from '@/auth/LoginPage'
import { ChatPage } from '@/features/chat/ChatPage'
import { MyRequestsPage } from '@/features/my-requests/MyRequestsPage'
import { RequestDetailPage } from '@/features/my-requests/RequestDetailPage'

export function makeQueryClient(): QueryClient {
  // Mặc định của TanStack Query giữ nguyên (lấy lại khi lấy lại tiêu điểm) — đúng luật ADR-018 cho query ngoài chủ đề tín hiệu.
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<AuthGate />}>
        <Route element={<Layout />}>
          <Route index element={<Navigate to="/chat" replace />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/my-requests" element={<MyRequestsPage />} />
          <Route path="/my-requests/:requestId" element={<RequestDetailPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Route>
    </Routes>
  )
}

export function App() {
  const client = useMemo(makeQueryClient, [])
  useEffect(() => {
    // Bất kỳ response UNAUTHENTICATED nào về sau: xoá bộ đệm query, về trang đăng nhập (06-structure.md mục 11).
    setUnauthenticatedHandler(() => {
      client.clear()
      if (window.location.pathname !== '/login') window.location.assign('/login')
    })
    return () => setUnauthenticatedHandler(null)
  }, [client])
  return (
    <QueryClientProvider client={client}>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </QueryClientProvider>
  )
}
