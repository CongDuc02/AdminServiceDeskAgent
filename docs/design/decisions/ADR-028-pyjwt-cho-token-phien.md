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

---

## Cập nhật — B3, 2026-10-05: những chỗ BUILD MODE đã chốt

ADR này để "tên thuật toán cụ thể, cách xoay secret và thời hạn token" cho BUILD MODE. B3 chốt phần code của chúng; quyết định thuật toán là của người triển khai và PO duyệt ở kế hoạch B3 (2026-10-05).

- **Thuật toán ký: `HS256`.** Là mặc định của `PyJWT`, và có độ dài khoá tối thiểu thấp nhất trong ba thuật toán HMAC: **32 byte** (`HS384` 48, `HS512` 64) — `docs/reference/pyjwt-hmac-key-length.md`, mục 1 và 4 (PyJWT 2.15.0; RFC 7518 mục 3.2). Loại `HS384`, `HS512`: tăng độ dài secret PO phải đặt trên Render mà không có tín hiệu đe doạ nào đòi.
- **Độ dài tối thiểu của `BO19_SESSION_SECRET`: 32 byte** sau mã hoá UTF-8 — đóng A-088. Hai lớp: bước kiểm khởi động #12 từ chối secret ngắn hơn (`STARTUP_12_SESSION_SECRET_TOO_SHORT`); và `PyJWT` được dựng với `enforce_minimum_key_length` nên không ký, không kiểm bằng khoá ngắn dù #12 bị bỏ qua. Độ ngẫu nhiên không kiểm được bằng độ dài — xem A-088.
- **Nội dung token đúng hai claim: `sub` (id nhân viên, uuid) và `exp`.** Không `iat`, không permission, không trường nào khác — ADR-013 và mục Consequences ở trên. `exp` = lúc cấp + 8 giờ, tuyệt đối, không gia hạn trượt (WV-17).
- **Kiểm token ghim thuật toán.** `jwt.decode(..., algorithms=["HS256"])` — danh sách cố định trong code, **không bao giờ** đọc `alg` từ header token để chọn thuật toán. Token `alg=none`, và token ký bằng thuật toán khác (kể cả `HS512` bằng đúng secret), bị từ chối. Bắt buộc có `sub` và `exp`. Có test cho cả ba (`backend/tests/test_session_token.py`).
- **Cookie:** `bo19_session`, `HttpOnly; Secure; SameSite=Strict; Path=/api`, `Max-Age` bằng thời hạn token — đúng mục Xác thực và chống CSRF của `05-api.md`.
