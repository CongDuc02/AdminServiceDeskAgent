# ADR-034 — Thư viện hash mật khẩu: `argon2-cffi` 25.1.0, dùng trực tiếp

**Trạng thái:** Accepted · **Duyệt:** PO, 2026-10-02 — kèm ba điều kiện ở mục Điều kiện duyệt · **Ngày:** 2026-10-02 · **Quyết định tại:** BUILD MODE, trước code đăng nhập của Sprint 1 · **Liên quan:** ADR-021 (họ hàm `argon2id`), A-048 (WV-16, WV-16b), ADR-030 (lockfile), mục AuthN của `09-security.md`, `docs/reference/argon2-cffi-parameters.md`, `docs/reference/owasp-password-storage-argon2id.md`

---

## Context

ADR-021 chọn họ hàm `argon2id`, và để tên cùng phiên bản thư viện cho BUILD MODE (`backend/pyproject.toml` ghi rõ `[CẦN XÁC MINH]`). Tham số đã chốt ở WV-16: `time_cost=2`, `memory_cost=19456` KiB, `parallelism=1` — cấu hình thứ hai của OWASP. WV-16b: tối đa 4 lần verify đồng thời trong một tiến trình `api`.

Ba ràng buộc của dự án:

1. **Lock có hash, image Linux, Docker từ máy Windows** (ADR-030, ADR-015). Gói nào cần biên dịch lúc cài thì image phải có trình biên dịch.
2. **`bo19_app` chỉ đọc `employee_credential`** (A-048, H1). Ứng dụng chỉ verify; hash mới sinh ở thao tác vận hành seed, chạy bằng `bo19_migrator`.
3. **Ít phụ thuộc là tốt hơn.** Mỗi gói thêm vào là một ghim, một hash, một chỗ CI phải kiểm.

## Options

- **A — `argon2-cffi` 25.1.0, dùng trực tiếp.**
- **B — `pwdlib` 0.3.1 kèm extra `argon2`.**
- **C — `passlib` 1.7.4 kèm extra `argon2`.**
- **D — thư viện chuẩn `hashlib`.**

### Đã kiểm — 2026-10-02

Mọi dữ kiện đọc từ metadata của wheel tải bằng `pip download`, hoặc từ phép chạy thật — không ghi từ trí nhớ.

| Phép kiểm | Kết quả |
|---|---|
| `hashlib` của Python 3.11.9 có argon2 không | **Không** — `algorithms_available` không có tên nào chứa `argon`; có `scrypt` |
| `pwdlib` 0.3.1, extra `argon2` | `Requires-Dist: argon2-cffi>=23.1.0; extra == 'argon2'` — tức là lớp bọc quanh A |
| `passlib` 1.7.4, extra `argon2` | `Requires-Dist: argon2-cffi (>=18.2.0) ; extra == 'argon2'` — cũng là lớp bọc quanh A |
| `argon2-cffi` 25.1.0 | `Requires-Dist: argon2-cffi-bindings`. `argon2-cffi-bindings` 26.1.0 có wheel dựng sẵn `cp310-abi3-manylinux_2_26_x86_64.manylinux_2_28_x86_64` |
| Khoá thử — thêm `argon2-cffi==25.1.0` vào `pyproject.toml`, cùng lệnh của ADR-030 | Lock thêm **đúng bốn gói**: `argon2-cffi` 25.1.0, `argon2-cffi-bindings` 26.1.0, `cffi` 2.1.1, `pycparser` 3.0 |
| Cài lock thử trong container `python:3.11-slim` — Debian, glibc 2.41 — bằng `pip install --require-hashes --no-deps`; hash rồi verify với `t=2, m=19456, p=1` | Cài từ wheel, **không biên dịch**. Chuỗi hash `argon2id`, `v=19`, `m=19456,t=2,p=1`; verify `True` |

Bộ nhớ và thời lượng verify đo ở mục Bộ nhớ đỉnh và thời lượng khi verify đồng thời của `docs/reference/argon2-cffi-parameters.md`. Đổi tham số không phá hash cũ — mục Đổi tham số — hash cũ còn verify được không của cùng tài liệu.

## Decision

**Đề xuất A — `argon2-cffi==25.1.0`, ghim trực tiếp trong `backend/pyproject.toml`.**

- **Chỉ một module dùng nó:** module xác thực của `api` gọi `verify`; thao tác vận hành seed gọi `hash`. Tham số đọc từ cấu hình — WV-16 — không viết cứng, cùng luật với mọi giá trị "chưa hiệu chỉnh".
- **Đề xuất kèm, chưa vào thiết kế:** một bước kiểm khởi động từ chối chạy khi tham số `argon2id` trong cấu hình thấp hơn WV-16 đã duyệt. Nếu PO duyệt, thêm vào mục Bước kiểm khởi động của `06-structure.md` trước khi viết code. Đổi tham số là đổi cấu hình kèm `CHANGELOG.md`, không phải đổi code.
- **WV-16b — trần 4 lần verify đồng thời** — là một semaphore của tiến trình bọc quanh lời gọi `verify`. Thư viện không có cơ chế này; dự án tự làm.
- **`check_needs_rehash`** — thư viện khuyên hash lại sau lần đăng nhập thành công. **Không dùng** trong ứng dụng, vì `bo19_app` không ghi được bảng credential (H1). Hash lại là thao tác vận hành.
- **Sau khi PO duyệt:** thêm ghim vào `backend/pyproject.toml`, sinh lại `backend/requirements-linux.lock` bằng đúng lệnh ở đầu file, ghi `CHANGELOG.md`.

## Consequences

**Tích cực**

- Lock chỉ thêm bốn gói, và cả bốn đều có wheel cho Linux — image không cần trình biên dịch.
- Một lớp duy nhất giữa dự án và hàm hash. Tham số, định dạng chuỗi hash, hành vi verify chính là của thư viện được đo trong tài liệu tham chiếu.
- **ADR-021 có một câu được thay bằng số đo:** câu "cần biên dịch phần mở rộng gốc ở hầu hết bản phân phối" — với đích của dự án là Linux x86_64 glibc từ 2.28 trở lên, có wheel dựng sẵn.

**Tiêu cực và cái phải chấp nhận**

- `argon2-cffi-bindings` là phần mở rộng gốc. Đổi image nền sang libc khác — ví dụ musl — thì phải kiểm lại có wheel không. Kiểm bằng bước CI cài lock trên Linux của ADR-030.
- Dự án tự làm trần verify đồng thời và tự kiểm tham số lúc khởi động — hai việc mà một lớp bọc như B hay C cũng không làm thay.

**Điều kiện đảo ngược**

- `argon2-cffi` ngừng phát hành bản dùng được, hay một bản mới đổi định dạng chuỗi hash → giữ bản đã ghim; nếu phải đổi thư viện thì chọn thư viện verify được chuỗi hash hiện có, kiểm bằng phép thử hash cũ trước khi đổi.
- Image nền không còn wheel cho `argon2-cffi-bindings` → xét lại cùng ADR-015.

## Rejected alternatives

**B — `pwdlib`.** Bọc quanh chính A — metadata của nó kéo `argon2-cffi` qua extra. Thêm một gói và một lớp API mà dự án không cần: chỉ có một hàm hash, một bộ tham số, và không có ý định chuyển hàm nhờ lớp bọc — đổi họ hàm phải có ADR mới theo ADR-021.

**C — `passlib`.** Cùng lý do với B: lớp bọc quanh A. Thêm nữa, ADR-021 đã loại `bcrypt`, nên phần lớn giá trị của một thư viện nhiều thuật toán không dùng tới.

**D — `hashlib`.** Python 3.11 không có argon2 trong thư viện chuẩn — đã kiểm. Chỉ có `scrypt`, mà ADR-021 đã loại.

## Điều kiện duyệt — PO, 2026-10-02

1. **Đính chính ADR-021** bằng một mục "Cập nhật 2026-10-02": trên đích của dự án không phải biên dịch phần mở rộng gốc. Không sửa nội dung gốc của ADR-021.
2. **Bước kiểm khởi động — #20 của mục Bước kiểm khởi động của `06-structure.md`:** tham số `argon2id` trong cấu hình thấp hơn WV-16 thì tiến trình từ chối chạy. **Không có ngoại lệ theo môi trường** — `dev` cũng vậy. Test cần nhanh thì **tự tạo hasher riêng** với tham số rẻ, không hạ cấu hình của ứng dụng.
3. **Phạm vi của WV-16b:** semaphore **theo tiến trình**. `combined_main` (ADR-033) chạy `api` và `worker` trong một tiến trình, nên dùng **chung một trần 4** cho cả hai — không phải 4 cho mỗi vai.

**Vị trí module xác thực** — nơi duy nhất gọi `verify` — chốt khi viết code đăng nhập của Sprint 1. Khi đó thêm một contract `forbidden` vào mục Luật import của `06-structure.md` để chỉ module đó và thao tác vận hành seed được import `argon2`.

## Open Questions

Không có.
