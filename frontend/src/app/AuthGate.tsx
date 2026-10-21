// Chặn mọi tuyến trừ /login: chưa đăng nhập (`GET /me` → 401) thì về /login, nhớ nơi định tới. Lỗi khác của `GET /me` hiện thông điệp của server.
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { traceIdOf, userMessage } from '@/api/errors'
import { useMe } from '@/auth'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Loading } from '@/components/Loading'

export function AuthGate() {
  const me = useMe()
  const location = useLocation()
  if (me.isPending) return <Loading />
  if (me.isError) return <ErrorMessage message={userMessage(me.error)} traceId={traceIdOf(me.error)} />
  if (!me.data) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  return <Outlet />
}
