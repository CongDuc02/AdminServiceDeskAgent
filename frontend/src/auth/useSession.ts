// Đăng nhập / đăng xuất (06-structure.md mục 11). Đăng xuất xoá bộ đệm query (không để dữ liệu người trước lộ cho người sau).
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { login, logout } from '@/api/endpoints/auth'
import { queryKeys } from '@/api/queryKeys'

export function useLogin() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ employeeCode, password }: { employeeCode: string; password: string }) => login(employeeCode, password),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: queryKeys.me })
    },
  })
}

export function useLogout() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => logout(),
    onSettled: () => {
      client.clear()
    },
  })
}
