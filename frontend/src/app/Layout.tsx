// Khung trang: dải chế độ thử nghiệm, thanh điều hướng theo permission (không theo vai trò), đăng xuất.
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { hasAnyPermission, hasPermission, useLogout, useMe } from '@/auth'
import { TestModeBanner } from '@/components/TestModeBanner'
import styles from '@/components/ui.module.css'

const CREATE = ['request.create', 'request.create_on_behalf']

export function Layout() {
  const me = useMe().data
  const logout = useLogout()
  const navigate = useNavigate()
  if (!me) return null
  return (
    <>
      <TestModeBanner mode={me.operating_mode} />
      <header style={{ display: 'flex', gap: '1rem', alignItems: 'center', padding: '0.75rem 1rem', borderBottom: '1px solid #ddd', flexWrap: 'wrap' }}>
        <strong>BO-19</strong>
        <nav style={{ display: 'flex', gap: '1rem', flex: 1, flexWrap: 'wrap' }}>
          {hasAnyPermission(me, CREATE) ? <NavLink to="/chat">Trò chuyện</NavLink> : null}
          {hasPermission(me, 'request.read_own') ? <NavLink to="/my-requests">Yêu cầu của tôi</NavLink> : null}
        </nav>
        <span className={styles.muted}>{me.employee.full_name}</span>
        <button
          type="button"
          className={`${styles.button} ${styles.buttonSecondary}`}
          onClick={() => logout.mutate(undefined, { onSettled: () => navigate('/login', { replace: true }) })}
        >
          Đăng xuất
        </button>
      </header>
      <Outlet />
    </>
  )
}
