// Đăng nhập, AuthGate, khung trang, tuyến lạ (06-structure.md mục 10.3, 11).
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { AppRoutes } from '@/app/App'
import { ENVELOPE, ME, SESSION } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'

const unauth = http.get('/api/v1/me', () => HttpResponse.json(ENVELOPE('UNAUTHENTICATED', 'Bạn chưa đăng nhập.'), { status: 401 }))
const auth = (me = ME) => http.get('/api/v1/me', () => HttpResponse.json(me))
const emptyChat = [
  http.post('/api/v1/chat-sessions', () => HttpResponse.json(SESSION, { status: 201 })),
  http.get(`/api/v1/chat-sessions/${SESSION.id}/messages`, () => HttpResponse.json({ items: [], next_cursor: null })),
]

describe('AuthGate', () => {
  it('chưa đăng nhập → về /login', async () => {
    server.use(unauth)
    renderWithProviders(<AppRoutes />, { route: '/my-requests' })
    expect(await screen.findByRole('heading', { name: 'Đăng nhập' })).toBeInTheDocument()
  })

  it('đã đăng nhập → vào được trang, thấy tên và dải chế độ thử nghiệm', async () => {
    server.use(auth(), ...emptyChat)
    renderWithProviders(<AppRoutes />, { route: '/chat' })
    expect(await screen.findByRole('heading', { name: 'Trò chuyện' })).toBeInTheDocument()
    expect(screen.getByRole('note')).toHaveTextContent('Chế độ thử nghiệm')
    expect(screen.getByText('NHÂN VIÊN GIẢ 01 (GIẢ)')).toBeInTheDocument()
  })

  it('PRODUCTION không có dải thử nghiệm', async () => {
    server.use(auth({ ...ME, operating_mode: 'PRODUCTION' }), ...emptyChat)
    renderWithProviders(<AppRoutes />, { route: '/chat' })
    await screen.findByRole('heading', { name: 'Trò chuyện' })
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })

  it('lỗi khác của GET /me hiện thông điệp NGUYÊN VĂN của server', async () => {
    server.use(http.get('/api/v1/me', () => HttpResponse.json(ENVELOPE('INTERNAL_ERROR', 'Hệ thống đang bảo trì.'), { status: 500 })))
    renderWithProviders(<AppRoutes />, { route: '/my-requests' })
    expect(await screen.findByRole('alert')).toHaveTextContent('Hệ thống đang bảo trì.')
  })
})

describe('thanh điều hướng theo permission, không theo vai trò', () => {
  it('chỉ có request.read_own → không thấy "Trò chuyện"', async () => {
    server.use(auth({ ...ME, permissions: ['request.read_own'] as unknown as typeof ME.permissions }), http.get('/api/v1/requests', () => HttpResponse.json({ items: [], next_cursor: null })))
    renderWithProviders(<AppRoutes />, { route: '/my-requests' })
    await screen.findByRole('heading', { name: 'Yêu cầu của tôi' })
    expect(screen.queryByRole('link', { name: 'Trò chuyện' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Yêu cầu của tôi' })).toBeInTheDocument()
  })
})

describe('đăng nhập', () => {
  it('thành công → vào /chat', async () => {
    let signedIn = false
    server.use(
      http.get('/api/v1/me', () => (signedIn ? HttpResponse.json(ME) : HttpResponse.json(ENVELOPE('UNAUTHENTICATED', 'Bạn chưa đăng nhập.'), { status: 401 }))),
      http.post('/api/v1/auth/session', async ({ request }) => {
        expect(await request.json()).toEqual({ employee_code: 'GIA-0001', password: 'mat-khau-gia' })
        expect(request.headers.get('X-BO19-CSRF')).toBe('1')
        signedIn = true
        return new HttpResponse(null, { status: 204 })
      }),
      ...emptyChat,
    )
    renderWithProviders(<AppRoutes />, { route: '/login' })
    await userEvent.type(await screen.findByLabelText('Mã nhân viên'), ' GIA-0001 ')
    await userEvent.type(screen.getByLabelText('Mật khẩu'), 'mat-khau-gia')
    await userEvent.click(screen.getByRole('button', { name: 'Đăng nhập' }))
    expect(await screen.findByRole('heading', { name: 'Trò chuyện' })).toBeInTheDocument()
  })

  it('sai thông tin → thông điệp của server, KHÔNG nói sai ở đâu, vẫn ở trang đăng nhập', async () => {
    server.use(
      unauth,
      http.post('/api/v1/auth/session', () => HttpResponse.json(ENVELOPE('INVALID_CREDENTIALS', 'Mã nhân viên hoặc mật khẩu không đúng.'), { status: 401 })),
    )
    renderWithProviders(<AppRoutes />, { route: '/login' })
    await userEvent.type(await screen.findByLabelText('Mã nhân viên'), 'GIA-0001')
    await userEvent.type(screen.getByLabelText('Mật khẩu'), 'sai')
    await userEvent.click(screen.getByRole('button', { name: 'Đăng nhập' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Mã nhân viên hoặc mật khẩu không đúng.')
    expect(screen.getByRole('heading', { name: 'Đăng nhập' })).toBeInTheDocument()
  })

  it('đã đăng nhập mà vào /login → chuyển đi; không bao giờ nhảy tới đường /api', async () => {
    server.use(auth(), ...emptyChat)
    renderWithProviders(
      <Routes>
        <Route path="*" element={<AppRoutes />} />
      </Routes>,
      { route: '/login' },
    )
    expect(await screen.findByRole('heading', { name: 'Trò chuyện' })).toBeInTheDocument()
  })
})

describe('tuyến SPA lạ (luật 404 phía client, O1-8)', () => {
  it('hiện "Không tìm thấy trang" — không phải trang trắng, không gọi API', async () => {
    server.use(auth())
    renderWithProviders(<AppRoutes />, { route: '/khong-co-trang-nay' })
    expect(await screen.findByRole('heading', { name: 'Không tìm thấy trang' })).toBeInTheDocument()
  })
})

describe('đăng xuất', () => {
  it('gọi DELETE /auth/session kèm CSRF rồi về /login', async () => {
    let csrf: string | null = null
    let signedOut = false
    server.use(
      http.get('/api/v1/me', () => (signedOut ? HttpResponse.json(ENVELOPE('UNAUTHENTICATED', 'Bạn chưa đăng nhập.'), { status: 401 }) : HttpResponse.json(ME))),
      http.delete('/api/v1/auth/session', ({ request }) => {
        csrf = request.headers.get('X-BO19-CSRF')
        signedOut = true
        return new HttpResponse(null, { status: 204 })
      }),
      ...emptyChat,
    )
    renderWithProviders(<AppRoutes />, { route: '/chat' })
    await userEvent.click(await screen.findByRole('button', { name: 'Đăng xuất' }))
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Đăng nhập' })).toBeInTheDocument())
    expect(csrf).toBe('1')
  })
})
