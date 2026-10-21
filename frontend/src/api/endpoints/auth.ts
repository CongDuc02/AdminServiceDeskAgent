// Nhóm endpoint xác thực — mục Endpoint của 05-api.md. Chỉ gọi qua transport/http.
import type { components } from '@/api/generated/openapi'
import { get, post, del } from '@/api/transport/http'

export type Me = components['schemas']['Me']

export function getMe(): Promise<Me> {
  return get<Me>('/me')
}

export function login(employeeCode: string, password: string): Promise<void> {
  return post<void>('/auth/session', { body: { employee_code: employeeCode, password } })
}

export function logout(): Promise<void> {
  return del<void>('/auth/session')
}
