// `GET /me`: người đang đăng nhập, permission hiệu lực, chế độ vận hành. 401 không phải lỗi hiển thị mà là "chưa đăng nhập" → `data = null`.
import { useQuery } from '@tanstack/react-query'
import { getMe, type Me } from '@/api/endpoints/auth'
import { ApiError } from '@/api/errors'
import { queryKeys } from '@/api/queryKeys'

export function useMe() {
  return useQuery<Me | null>({
    queryKey: queryKeys.me,
    queryFn: async () => {
      try {
        return await getMe()
      } catch (e) {
        if (e instanceof ApiError && e.code === 'UNAUTHENTICATED') return null
        throw e
      }
    },
    retry: false,
    staleTime: 60_000,
  })
}
