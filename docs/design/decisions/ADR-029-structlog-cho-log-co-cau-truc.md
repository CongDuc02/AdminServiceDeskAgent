# ADR-029 — `structlog` cho log có cấu trúc

**Trạng thái:** Accepted · **Ngày:** 2026-09-26 · **Quyết định tại:** PO, khi nhận đợt sửa 3 sau Phase 13 — dòng `structlog` còn treo của AUD-25 (`13-audit.md`) · **Liên quan:** mục Log schema của `11-ops.md`, ADR-024 (`trace_id`), mục Mask trong log kỹ thuật của `09-security.md`, gói `bo19.observability` ở mục Cây backend của `06-structure.md`, `backend/pyproject.toml`

---

## Context

`11-ops.md` mục Log schema đòi log là JSON, mỗi sự kiện là **mã cộng trường có kiểu**, mang `trace_id` (ADR-024), và mask giá trị theo `slot_sensitivity` (`09-security.md`). `06-structure.md` đặt ba việc đó ở `bo19.observability`: `log.py` — lối ghi log duy nhất; `masking.py`; `handler.py` — handler JSON duy nhất gắn vào root logger. Skeleton ghim `structlog==25.4.0` mà không tài liệu nào chọn (AUD-25).

## Options

- **A — `structlog`**, cắm vào `logging` của thư viện chuẩn: sự kiện là từ điển có tên, các bước xử lý — gắn `trace_id`, mask, xuất JSON — xếp thành một chuỗi.
- **B — Chỉ `logging` của thư viện chuẩn, tự viết formatter JSON** trong `handler.py`.
- **C — Một thư viện formatter JSON** cắm vào `logging` của thư viện chuẩn, không đổi cách gọi log.

## Decision

**Chọn A** — quyết định của PO, 2026-09-26.

- Chỉ `bo19.observability.log` gọi `structlog`. Các gói khác gọi `log.py`, không import `structlog` trực tiếp — cùng khuôn "một lối vào" của `ai_gateway`.
- Log của thư viện bên thứ ba vẫn đi qua `logging` chuẩn và `handler.py`, bị rút về tên logger, mức và kiểu lỗi (mục Cây backend của `06-structure.md`).
- Mask chạy như **một bước trong chuỗi**, trước bước xuất JSON. Không có đường nào xuất bản ghi mà bỏ qua bước mask.
- Giữ ghim `structlog==25.4.0`. Phiên bản này **có trên PyPI**, kiểm bằng `pip index versions structlog` ngày 2026-09-26. Chưa cài thử.

## Consequences

**Tích cực**

- "Sự kiện = mã + trường có kiểu" là cách gọi tự nhiên của thư viện, không phải quy ước phải tự giữ.
- `trace_id` theo `contextvar` (`trace.py`) gắn vào mọi bản ghi bằng một bước chung.

**Tiêu cực và cái phải chấp nhận**

- Hai đường log cùng tồn tại — `structlog` cho mã của dự án, `logging` chuẩn cho thư viện — và phải cùng ra một định dạng JSON. Cấu hình sai thì một đường xuất khác khuôn. Chỗ bắt: bước kiểm khởi động và test của `observability`, BUILD MODE.
- Thêm một phụ thuộc so với phương án B.

**Điều kiện đảo ngược**

- Công cụ APM chọn ở A-069 đòi một thư viện log riêng của nó — xét lại cùng lúc với ADR-024.

## Rejected alternatives

**B — Chỉ `logging` chuẩn.** Không thêm phụ thuộc, nhưng "mã + trường có kiểu" thành quy ước tự giữ: gọi `logger.info` với chuỗi tự do vẫn chạy, và log mang văn bản tự do là đúng thứ `11-ops.md` cấm.

**C — Formatter JSON cho `logging` chuẩn.** Giải được vế định dạng, không giải vế cách gọi — cùng điểm yếu của B.
