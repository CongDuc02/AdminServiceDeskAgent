# ADR-028 — `PyJWT` cho token phiên stateless

**Trạng thái:** Accepted · **Ngày:** 2026-09-26 · **Quyết định tại:** PO, khi nhận đợt sửa 3 sau Phase 13 — dòng `python-jose` còn treo của AUD-25 (`13-audit.md`) · **Liên quan:** ADR-013 (phiên không lưu DB, token ký bằng secret phía server), ADR-021 (hash mật khẩu — không nói gì về token), mục Auth flow của `06-structure.md`, `backend/pyproject.toml`

---

## Context

ADR-013 chốt phiên **stateless**: cookie `bo19_session` mang một token ký bằng secret phía server, chứa định danh nhân viên và thời điểm hết hạn. ADR-013 không chọn định dạng token hay thư viện. Skeleton ghim `python-jose[cryptography]` mà không tài liệu nào chọn — AUD-25 ghi dòng này là "lựa chọn thư viện chưa có ở tài liệu nào". ADR-021 chỉ về hash mật khẩu, không chỉ định gì cho token.

Việc cần: ký và kiểm một token nhỏ bằng **một secret đối xứng phía server**, có hạn dùng. Không cần mã hoá nội dung token, không cần khoá công khai, không cần bên thứ ba kiểm token.

## Options

- **A — `PyJWT`.** Token dạng JWT, ký bằng HMAC với secret phía server.
- **B — `python-jose`.** Cũng làm được JWT. Tên thư viện là bộ JOSE — gồm cả phần mã hoá và quản lý khoá mà việc ở trên không cần.
- **C — Tự ký bằng `hmac` của thư viện chuẩn.** Không thêm phụ thuộc: ghép định danh, hạn dùng, chữ ký HMAC.

## Decision

**Chọn A** — quyết định của PO, 2026-09-26.

- Ký bằng HMAC với secret phía server, đúng ADR-013. Không dùng thuật toán khoá công khai, nên không cần phần mở rộng mật mã của thư viện.
- Ghim `PyJWT==2.15.0` ở `backend/pyproject.toml`. Phiên bản này **có trên PyPI**, kiểm bằng `pip index versions PyJWT` ngày 2026-09-26. Chưa cài thử — DESIGN MODE, chưa có lockfile.
- Tên thuật toán cụ thể, cách xoay secret và thời hạn token: BUILD MODE, theo A-048 và mục Secret management trên Render của `09-security.md`.

## Consequences

**Tích cực**

- Chỉ kéo vào phần của thư viện mà việc ở trên dùng.
- Định dạng token có sẵn cách kiểm hạn dùng, không tự viết.

**Tiêu cực và cái phải chấp nhận**

- Một phụ thuộc cho một việc mà thư viện chuẩn làm được (phương án C).
- Token JWT mang nội dung đọc được khi giải mã base64. ADR-013 đã giới hạn nội dung ở định danh nhân viên và thời điểm hết hạn — không đặt thêm trường nào vào token.

**Điều kiện đảo ngược**

- Phiên chuyển sang lưu DB (đảo ngược vế stateless của ADR-013) — khi đó cookie chỉ cần một id ngẫu nhiên, không cần thư viện ký.

## Rejected alternatives

**B — `python-jose`.** Làm được việc, nhưng mang cả bộ JOSE mà việc ở trên không dùng. PO chọn A.

**C — Tự ký bằng `hmac`.** Không thêm phụ thuộc. Loại vì phải tự thiết kế định dạng token, tự kiểm hạn, tự so chữ ký đúng cách — những chỗ dễ sai mà thư viện đã làm sẵn.
