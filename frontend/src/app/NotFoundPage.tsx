// Tuyến SPA lạ (luật 404 phía client, O1-8): `api` trả `index.html` cho mọi GET lạ ngoài /api, nên chính client phải nói "không tìm thấy". Đường /api lạ không bao giờ tới đây (server trả ErrorEnvelope).
import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return (
    <main style={{ padding: '2rem 1rem', textAlign: 'center' }}>
      <h1>Không tìm thấy trang</h1>
      <p>
        <Link to="/">Về trang chính</Link>
      </p>
    </main>
  )
}
