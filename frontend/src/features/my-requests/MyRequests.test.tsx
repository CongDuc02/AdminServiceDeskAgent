// Yêu cầu của tôi: danh sách, chi tiết (slot, độ nhạy, nguồn gốc), xác nhận từng slot, gửi, văn bản và tải bản FINAL, và luật làm mới tạm thời (ADR-018, cập nhật 2026-10-21).
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { DOC_ID, ENVELOPE, REQUEST_ID, RENDER_ID, detail, slot, summary } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import { MyRequestsPage } from './MyRequestsPage'
import { RequestDetailPage } from './RequestDetailPage'
import { DETAIL_POLL_MS, shouldPoll } from './useMyRequests'

const detailUrl = `/api/v1/requests/${REQUEST_ID}`
const page = () =>
  renderWithProviders(
    <Routes>
      <Route path="/my-requests" element={<MyRequestsPage />} />
      <Route path="/my-requests/:requestId" element={<RequestDetailPage />} />
    </Routes>,
    { route: `/my-requests/${REQUEST_ID}` },
  )

const proposed = (name: string, label: string, version: number) => slot({ slot_name: name as never, label, value: `giá trị ${label}`, value_status: 'PROPOSED', row_version: version, confirmed_at: null, provenance: null, sensitivity: 'INT', source: 'USER_INPUT' })

describe('danh sách', () => {
  it('hiện tên loại, status_label của server, thời gian; phân trang bằng cursor', async () => {
    const cursors: (string | null)[] = []
    server.use(
      http.get('/api/v1/requests', ({ request }) => {
        const u = new URL(request.url)
        expect(u.searchParams.get('scope')).toBe('OWN')
        cursors.push(u.searchParams.get('cursor'))
        return u.searchParams.get('cursor')
          ? HttpResponse.json({ items: [summary({ id: '66666666-6666-4666-8666-666666666666', status_label: 'Đã hoàn tất' })], next_cursor: null })
          : HttpResponse.json({ items: [summary({ status_label: 'Đang soạn' })], next_cursor: 'c1' })
      }),
    )
    renderWithProviders(<MyRequestsPage />)
    expect(await screen.findByText('Đang soạn')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Giấy xác nhận công tác' })).toHaveAttribute('href', `/my-requests/${REQUEST_ID}`)
    await userEvent.click(screen.getByRole('button', { name: 'Tải thêm' }))
    expect(await screen.findByText('Đã hoàn tất')).toBeInTheDocument()
    expect(cursors).toEqual([null, 'c1'])
  })

  it('rỗng → gợi ý; lỗi → thông điệp của server', async () => {
    server.use(http.get('/api/v1/requests', () => HttpResponse.json({ items: [], next_cursor: null })))
    const { unmount } = renderWithProviders(<MyRequestsPage />)
    expect(await screen.findByText(/chưa có yêu cầu nào/)).toBeInTheDocument()
    unmount()
    server.use(http.get('/api/v1/requests', () => HttpResponse.json(ENVELOPE('INTERNAL_ERROR', 'Không tải được danh sách.'), { status: 500 })))
    renderWithProviders(<MyRequestsPage />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Không tải được danh sách.')
  })
})

describe('chi tiết — thông tin', () => {
  it('slot: nhãn, giá trị, độ nhạy, nguồn gốc HR_PROFILE, đã xác nhận', async () => {
    server.use(
      http.get(detailUrl, () =>
        HttpResponse.json(detail({ slots: [slot({}), slot({ slot_name: 'national_id' as never, label: 'Số căn cước', value: '012345678901', sensitivity: 'RES' }), slot({ slot_name: 'purpose' as never, label: 'Mục đích', erased: true, value: null, value_status: 'ERASED', sensitivity: 'RES' })] })),
      ),
    )
    page()
    expect(await screen.findByRole('heading', { name: /Giấy xác nhận công tác/ })).toBeInTheDocument()
    expect(screen.getByText('NGUYỄN VĂN A (GIẢ)')).toBeInTheDocument()
    expect(screen.getByText('Dữ liệu cá nhân')).toBeInTheDocument()
    expect(screen.getByText('Dữ liệu hạn chế', { selector: 'span' })).toBeInTheDocument()
    expect(screen.getAllByText(/Nguồn: TEST_FAKE, đồng bộ/).length).toBe(3) // cả ba slot HR_PROFILE của fixture mang nguồn
    expect(screen.getByText('nội dung đã xoá')).toBeInTheDocument()
    expect(screen.getAllByText('Đã xác nhận').length).toBeGreaterThan(0)
  })

  it('không có giá trị nào bị ghi ra console', async () => {
    const spies = (['log', 'info', 'warn', 'error', 'debug'] as const).map((m) => vi.spyOn(console, m).mockImplementation(() => {}))
    server.use(http.get(detailUrl, () => HttpResponse.json(detail({ slots: [slot({ slot_name: 'national_id' as never, label: 'Số căn cước', value: '012345678901', sensitivity: 'RES' })] }))))
    page()
    await screen.findByText('012345678901')
    for (const s of spies) expect(JSON.stringify(s.mock.calls)).not.toContain('012345678901')
  })

  it('NOT_FOUND (yêu cầu của người khác hoặc không tồn tại) hiện thông điệp của server', async () => {
    server.use(http.get(detailUrl, () => HttpResponse.json(ENVELOPE('NOT_FOUND', 'Không tìm thấy yêu cầu.'), { status: 404 })))
    page()
    expect(await screen.findByRole('alert')).toHaveTextContent('Không tìm thấy yêu cầu.')
  })
})

describe('xác nhận slot', () => {
  const withProposals = () => detail({ slots: [slot({}), proposed('department_name', 'Phòng ban', 4), proposed('job_title', 'Chức danh', 7)], unconfirmed_slots: ['department_name', 'job_title'] as never, submit_ready: false })

  it('xác nhận một slot: gửi đúng slot_name và expected_row_version, rồi cập nhật từ response', async () => {
    let body: unknown = null
    server.use(
      http.get(detailUrl, () => HttpResponse.json(withProposals())),
      http.post(`${detailUrl}/actions/confirm-slots`, async ({ request }) => {
        body = await request.json()
        expect(request.headers.get('X-BO19-CSRF')).toBe('1')
        return HttpResponse.json(detail({ slots: [slot({}), slot({ slot_name: 'department_name' as never, label: 'Phòng ban', value: 'giá trị Phòng ban' }), proposed('job_title', 'Chức danh', 7)] }))
      }),
    )
    page()
    const row = (await screen.findByText('Phòng ban')).closest('tr')!
    await userEvent.click(within(row).getByRole('button', { name: 'Xác nhận' }))
    await waitFor(() => expect(body).toEqual({ confirmations: [{ slot_name: 'department_name', expected_row_version: 4 }] }))
    await waitFor(() => expect(within(screen.getByText('Phòng ban').closest('tr')!).queryByRole('button', { name: 'Xác nhận' })).not.toBeInTheDocument())
  })

  it('"Xác nhận tất cả đề xuất" gửi mọi slot PROPOSED một lần', async () => {
    let body: { confirmations: unknown[] } | null = null
    server.use(
      http.get(detailUrl, () => HttpResponse.json(withProposals())),
      http.post(`${detailUrl}/actions/confirm-slots`, async ({ request }) => {
        body = (await request.json()) as { confirmations: unknown[] }
        return HttpResponse.json(detail())
      }),
    )
    page()
    await userEvent.click(await screen.findByRole('button', { name: 'Xác nhận tất cả đề xuất' }))
    await waitFor(() => expect(body?.confirmations).toEqual([{ slot_name: 'department_name', expected_row_version: 4 }, { slot_name: 'job_title', expected_row_version: 7 }]))
  })

  it('SLOT_VALUE_STALE: hiện thông điệp của server và lấy lại chi tiết', async () => {
    let gets = 0
    server.use(
      http.get(detailUrl, () => {
        gets++
        return HttpResponse.json(withProposals())
      }),
      http.post(`${detailUrl}/actions/confirm-slots`, () => HttpResponse.json(ENVELOPE('SLOT_VALUE_STALE', 'Giá trị vừa được cập nhật, hãy xem lại rồi xác nhận.'), { status: 409 })),
    )
    page()
    const row = (await screen.findByText('Phòng ban')).closest('tr')!
    await userEvent.click(within(row).getByRole('button', { name: 'Xác nhận' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Giá trị vừa được cập nhật, hãy xem lại rồi xác nhận.')
    await waitFor(() => expect(gets).toBeGreaterThanOrEqual(2))
  })

  it('yêu cầu đã gửi thì không có nút xác nhận', async () => {
    server.use(http.get(detailUrl, () => HttpResponse.json({ ...withProposals(), status: 'SUBMITTED' })))
    page()
    await screen.findByText('Phòng ban')
    expect(screen.queryByRole('button', { name: 'Xác nhận' })).not.toBeInTheDocument()
    expect(screen.getAllByText('Chờ bạn xác nhận', { selector: 'span' })).toHaveLength(2)
  })
})

describe('gửi yêu cầu', () => {
  it('chưa đủ điều kiện: liệt kê điều còn thiếu bằng nhãn slot, nút bị khoá', async () => {
    server.use(http.get(detailUrl, () => HttpResponse.json(detail({ slots: [slot({}), slot({ slot_name: 'purpose' as never, label: 'Mục đích', value: null, value_status: null, row_version: null })], missing_slots: ['purpose'] as never, unconfirmed_slots: ['full_name'] as never, failed_rules: [{ slot_name: 'recipient_org', rule_code: 'MIN_LENGTH' }] as never, submit_ready: false }))))
    page()
    expect(await screen.findByText('Còn thiếu: Mục đích')).toBeInTheDocument()
    expect(screen.getByText('Chưa xác nhận: Họ và tên')).toBeInTheDocument()
    expect(screen.getByText('Chưa đạt kiểm tra: recipient_org')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Gửi yêu cầu' })).toBeDisabled()
  })

  it('đủ điều kiện: gửi expected_row_version và Idempotency-Key; thành công thì lấy lại chi tiết', async () => {
    let captured: { key: string | null; body: unknown } | null = null
    let state = detail()
    server.use(
      http.get(detailUrl, () => HttpResponse.json(state)),
      http.post(`${detailUrl}/actions/submit`, async ({ request }) => {
        captured = { key: request.headers.get('Idempotency-Key'), body: await request.json() }
        state = detail({ status: 'SUBMITTED', status_label: 'Đã gửi' })
        return HttpResponse.json({ decision_record_id: 'd', kind: 'SUBMITTED', created_at: '2026-10-21T01:00:00Z', request: state, document: null })
      }),
    )
    page()
    await userEvent.click(await screen.findByRole('button', { name: 'Gửi yêu cầu' }))
    expect(await screen.findByText('Đã gửi')).toBeInTheDocument()
    expect(captured).toMatchObject({ body: { expected_row_version: 3 } })
    expect(captured!.key).toMatch(/^[0-9a-f-]{36}$/)
    expect(screen.queryByRole('button', { name: 'Gửi yêu cầu' })).not.toBeInTheDocument()
  })

  it('lỗi mạng rồi thử lại: dùng CÙNG Idempotency-Key; lỗi nghiệp vụ rồi thử lại: khoá MỚI', async () => {
    const keys: (string | null)[] = []
    let n = 0
    server.use(
      http.get(detailUrl, () => HttpResponse.json(detail())),
      http.post(`${detailUrl}/actions/submit`, ({ request }) => {
        keys.push(request.headers.get('Idempotency-Key'))
        n++
        if (n === 1) return HttpResponse.error()
        if (n === 2) return HttpResponse.json(ENVELOPE('STATE_CONFLICT', 'Yêu cầu đã đổi, hãy tải lại.'), { status: 409 })
        return HttpResponse.json(ENVELOPE('REQUEST_NOT_READY', 'Chưa đủ điều kiện.'), { status: 422 })
      }),
    )
    page()
    const send = async () => userEvent.click(await screen.findByRole('button', { name: 'Gửi yêu cầu' }))
    await send()
    await waitFor(() => expect(keys.length).toBe(1))
    await screen.findByRole('alert')
    await send()
    await waitFor(() => expect(keys.length).toBe(2))
    await send()
    await waitFor(() => expect(keys.length).toBe(3))
    expect(keys[1]).toBe(keys[0])
    expect(keys[2]).not.toBe(keys[1])
  })
})

describe('văn bản và tải bản FINAL', () => {
  const issued = { id: DOC_ID, status: 'ISSUED', status_label: 'Đã phát hành', issue_in_progress: false, document_number: 'TRIAL-001/2026/THU-NGHIEM', issued_date: '2026-10-21', final_render_id: RENDER_ID }

  it('chưa phát hành: hiện trạng thái do server trả, KHÔNG có số, KHÔNG có nút tải', async () => {
    server.use(http.get(detailUrl, () => HttpResponse.json(detail({ status: 'IN_REVIEW', documents: [{ ...issued, status: 'SEALED', status_label: 'Đang cấp số và phát hành', issue_in_progress: true, document_number: null, issued_date: null, final_render_id: null }] as never }))))
    page()
    expect(await screen.findByText('Đang cấp số và phát hành')).toBeInTheDocument()
    expect(screen.queryByText(/Số:/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Tải bản PDF' })).not.toBeInTheDocument()
  })

  it('đã phát hành: hiện số, ngày; bấm tải gọi đúng endpoint format=pdf và lưu tệp', async () => {
    let url: URL | null = null
    server.use(
      http.get(detailUrl, () => HttpResponse.json(detail({ status: 'FULFILLED', status_label: 'Hoàn tất', documents: [issued] as never }))),
      http.get(`/api/v1/documents/${DOC_ID}/renders/${RENDER_ID}/file`, ({ request }) => {
        url = new URL(request.url)
        return new HttpResponse(new Uint8Array([37, 80, 68, 70]), { headers: { 'Content-Type': 'application/pdf' } })
      }),
    )
    const anchor = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    page()
    expect(await screen.findByText(/Số: TRIAL-001\/2026\/THU-NGHIEM/)).toBeInTheDocument()
    expect(screen.getByText(/Ngày:/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Tải bản PDF' }))
    await waitFor(() => expect(anchor).toHaveBeenCalled())
    expect(url!.searchParams.get('format')).toBe('pdf')
  })

  it('FILE_UNAVAILABLE: thông điệp của server, không phải trang JSON thô', async () => {
    server.use(
      http.get(detailUrl, () => HttpResponse.json(detail({ status: 'FULFILLED', documents: [issued] as never }))),
      http.get(`/api/v1/documents/${DOC_ID}/renders/${RENDER_ID}/file`, () => HttpResponse.json(ENVELOPE('FILE_UNAVAILABLE', 'Tệp tạm thời không tải được, vui lòng thử lại.'), { status: 503 })),
    )
    page()
    await userEvent.click(await screen.findByRole('button', { name: 'Tải bản PDF' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Tệp tạm thời không tải được, vui lòng thử lại.')
    expect(screen.getByRole('button', { name: 'Tải bản PDF' })).toBeEnabled()
  })
})

describe('làm mới tạm thời tới GET /signals (ADR-018, 2026-10-21)', () => {
  it('shouldPoll: chờ hệ thống/cán bộ, hoặc còn văn bản chưa cuối', () => {
    for (const status of ['SUBMITTED', 'IN_REVIEW', 'APPROVED']) expect(shouldPoll({ status, documents: [] } as never), status).toBe(true)
    for (const status of ['DRAFT', 'NEEDS_INFO', 'CHANGES_REQUESTED', 'FULFILLED', 'REJECTED', 'CANCELLED', 'EXPIRED']) expect(shouldPoll({ status, documents: [] } as never), status).toBe(false)
    expect(shouldPoll({ status: 'CHANGES_REQUESTED', documents: [{ status: 'SIGNED' }] } as never)).toBe(true) // còn văn bản chưa cuối
    expect(shouldPoll({ status: 'FULFILLED', documents: [{ status: 'ISSUED' }] } as never)).toBe(false)
    expect(shouldPoll({ status: 'FULFILLED', documents: [{ status: 'ISSUED' }, { status: 'PENDING_SIGNATURE' }] } as never)).toBe(true)
    expect(shouldPoll(undefined)).toBe(false)
    expect(DETAIL_POLL_MS).toBe(10_000)
  })

  it('trang chi tiết tự lấy lại sau 10 s khi đang chờ và dừng khi đã cuối', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      let gets = 0
      server.use(
        http.get(detailUrl, () => {
          gets++
          return HttpResponse.json(gets === 1 ? detail({ status: 'IN_REVIEW', status_label: 'Đang xét duyệt' }) : detail({ status: 'FULFILLED', status_label: 'Hoàn tất', documents: [{ id: DOC_ID, status: 'ISSUED', status_label: 'Đã phát hành', issue_in_progress: false, document_number: 'S-1', issued_date: '2026-10-21', final_render_id: RENDER_ID }] as never }))
        }),
      )
      page()
      await screen.findByText('Đang xét duyệt')
      await vi.advanceTimersByTimeAsync(DETAIL_POLL_MS + 100)
      expect(await screen.findByText('Hoàn tất')).toBeInTheDocument()
      const after = gets
      await vi.advanceTimersByTimeAsync(DETAIL_POLL_MS * 3)
      expect(gets).toBe(after) // đã cuối: không hỏi nữa
    } finally {
      vi.useRealTimers()
    }
  })

  it('đang ở DRAFT thì không polling', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      let gets = 0
      server.use(http.get(detailUrl, () => (gets++, HttpResponse.json(detail()))))
      page()
      await screen.findByText('Họ và tên')
      await vi.advanceTimersByTimeAsync(DETAIL_POLL_MS * 3)
      expect(gets).toBe(1)
    } finally {
      vi.useRealTimers()
    }
  })
})
