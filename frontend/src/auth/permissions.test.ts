import { describe, expect, it } from 'vitest'
import { ME } from '@/test/fixtures'
import { hasAnyPermission, hasPermission } from './permissions'

describe('permission hiệu lực (D-005: theo permission, không theo vai trò)', () => {
  it('có / không có', () => {
    expect(hasPermission(ME, 'request.create')).toBe(true)
    expect(hasPermission(ME, 'document.issue')).toBe(false)
  })
  it('chưa đăng nhập → không có gì', () => {
    expect(hasPermission(null, 'request.create')).toBe(false)
    expect(hasPermission(undefined, 'request.create')).toBe(false)
    expect(hasAnyPermission(null, ['request.create'])).toBe(false)
  })
  it('hasAnyPermission', () => {
    expect(hasAnyPermission(ME, ['document.issue', 'request.create'])).toBe(true)
    expect(hasAnyPermission(ME, ['document.issue', 'document.sign'])).toBe(false)
    expect(hasAnyPermission(ME, [])).toBe(false)
  })
  it('khớp từng chuỗi, không khớp tiền tố', () => {
    expect(hasPermission(ME, 'request.')).toBe(false)
    expect(hasPermission(ME, 'request.create_on_behalf')).toBe(false)
  })
})
