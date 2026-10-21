// Ẩn hiện theo permission hiệu lực của `Me`, KHÔNG theo tên vai trò (D-005). Ẩn hiện ở giao diện chỉ là tiện ích; `api` mới là nơi kiểm.
import type { Me } from '@/api/endpoints/auth'

export function hasPermission(me: Me | null | undefined, code: string): boolean {
  return !!me && (me.permissions as readonly string[]).includes(code)
}

export function hasAnyPermission(me: Me | null | undefined, codes: readonly string[]): boolean {
  return codes.some((c) => hasPermission(me, c))
}
