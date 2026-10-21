// /login (06-structure.md mục 11): mã nhân viên + mật khẩu. Sai thông tin → thông điệp của server, KHÔNG nói sai ở đâu (một mã INVALID_CREDENTIALS cho cả hai).
import { useState, type FormEvent } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { traceIdOf, userMessage } from '@/api/errors'
import { ErrorMessage } from '@/components/ErrorMessage'
import styles from '@/components/ui.module.css'
import { useLogin } from '@/auth/useSession'
import { useMe } from '@/auth/useMe'

export function LoginPage() {
  const me = useMe()
  const login = useLogin()
  const location = useLocation()
  const [employeeCode, setEmployeeCode] = useState('')
  const [password, setPassword] = useState('')

  if (me.data) {
    const from = (location.state as { from?: string } | null)?.from
    return <Navigate to={from && from.startsWith('/') && !from.startsWith('/api') ? from : '/chat'} replace />
  }

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    login.mutate({ employeeCode: employeeCode.trim(), password })
  }

  return (
    <main style={{ maxWidth: 360, margin: '4rem auto', padding: '0 1rem' }}>
      <h1>Đăng nhập</h1>
      <form onSubmit={onSubmit}>
        <p>
          <label>
            Mã nhân viên
            <br />
            <input name="employee_code" autoComplete="username" value={employeeCode} onChange={(e) => setEmployeeCode(e.target.value)} required style={{ width: '100%' }} />
          </label>
        </p>
        <p>
          <label>
            Mật khẩu
            <br />
            <input name="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required style={{ width: '100%' }} />
          </label>
        </p>
        {login.isError ? <ErrorMessage message={userMessage(login.error)} traceId={traceIdOf(login.error)} /> : null}
        <button type="submit" className={styles.button} disabled={login.isPending}>
          {login.isPending ? 'Đang đăng nhập…' : 'Đăng nhập'}
        </button>
      </form>
    </main>
  )
}
