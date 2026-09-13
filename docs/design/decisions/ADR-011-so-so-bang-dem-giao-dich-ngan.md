# ADR-011 — Sổ số văn bản: bảng đếm khoá dòng trong một giao dịch ngắn riêng, định dạng số là cấu hình

**Trạng thái:** Accepted · **Ngày:** 2026-09-12 · **Quyết định tại:** Phase 4 — Data Architecture · **Liên quan:** mục Cấp số văn bản và mục Chế độ phi sản xuất của `00-domain.md`, D-008, D-009, ADR-001, AC của F3 trong `01-prd.md`, mục Tool Registry của `03-agents.md`, A-009, A-041

---

## Context

Ràng buộc đã chốt, không thương lượng:

- `document_number` được cấp **đúng một lần**, tại lúc `document` chuyển sang `ISSUED`, nguyên tử trên `document_register`. Hai lệnh phát hành đồng thời không bao giờ nhận cùng một số.
- Số đã cấp mà không gắn được với văn bản nào thì chuyển `VOIDED` kèm lý do và **không bao giờ tái sử dụng**. Sổ ưu tiên tính giải trình được hơn tính liên tục.
- Định dạng số **cấu hình được ngay từ đầu**. Ký hiệu chứa viết tắt tên cơ quan nên hardcode là sai trong mọi trường hợp (D-008, ADR-001). Giá trị cụ thể còn `TBD` (A-009).
- Hai dải `TRIAL` và `OFFICIAL` **không dùng chung bộ đếm** (D-009).
- Đánh số theo năm, reset đầu năm — vẫn là giả định (A-009).

Phase 3 đã chốt **nơi** cấp số: node `finalize_issue` trong `queue_worker`, với thứ tự (1) `document_number_assign` commit riêng → (2) render bản cuối và xuất PDF → (3) kiểm `approved_content_hash` → (4) giao dịch chuyển `ISSUED`. Bước (2) chạm `object_storage` và có thời lượng không cố định (A-025, A-031).

Chưa biết: tổ chức dùng một sổ chung cho mọi loại văn bản hay mỗi loại một sổ.

## Options

**A — Sequence object của PostgreSQL**, một sequence cho mỗi (sổ, dải, kỳ).

**B — Bảng đếm**, một dòng cho mỗi (sổ, dải, kỳ). Tăng bằng một câu `UPDATE` khoá dòng, **trong cùng giao dịch** với việc ghi dòng sổ.

**C — `MAX(seq) + 1`** trên bảng dòng sổ, dựa vào ràng buộc `UNIQUE` để phát hiện va chạm rồi thử lại.

## Decision

**Chọn B.** Bốn bảng, chi tiết ở mục Sổ số văn bản của `04-data.md`: `document_register` (sổ, ký hiệu, chu kỳ reset), `document_register_format` (mẫu định dạng theo sổ và dải, chỉ thêm, không sửa), `document_register_counter`, `document_register_entry`.

- **Cấp số là một giao dịch ngắn chỉ gồm:** bảo đảm dòng đếm của kỳ tồn tại → tăng bộ đếm (khoá dòng) → ghi `document_register_entry` ở `ASSIGNED` với chuỗi số đã định dạng → ghi `audit_event` → commit.
- **Không bao giờ giữ khoá dòng bộ đếm xuyên qua bước render và upload.** Khoá được thả khi giao dịch cấp số commit, trước khi bước (2) của `finalize_issue` bắt đầu. Giữ khoá qua một thao tác có thời lượng không cố định thì mọi lệnh phát hành khác trên cùng sổ phải xếp hàng sau một lần upload chậm. Thất bại sau khi đã commit thì dòng sổ chuyển `VOIDED` kèm lý do, trong một giao dịch riêng.
- **Tương đương phải giữ:** một giá trị `seq` tồn tại **khi và chỉ khi** có một dòng `document_register_entry` mang nó, vì việc tăng bộ đếm và việc ghi dòng sổ cùng commit hoặc cùng rollback. Lỗ hổng số chỉ phát sinh qua `VOIDED`, và luôn có lý do.
- **Idempotent theo `document_id`:** mỗi `document` có tối đa một dòng `ASSIGNED` (partial unique index). Lần thử lại của `finalize_issue` trả lại chính dòng đó, không lấy số mới.
- **Dải:** khoá của bộ đếm gồm `series`, nên `TRIAL` và `OFFICIAL` không bao giờ chung bộ đếm. Series của dòng sổ buộc phải khớp `operating_mode` đã ghim trên `document` bằng **khoá ngoại ghép**, không bằng kiểm trong code.
- **Định dạng:** mẫu dùng token (`{seq}`, `{year}`, `{symbol}` — tập token đầy đủ ở `04-data.md`). Chuỗi số đã định dạng được **lưu nguyên trên dòng sổ** cùng id của mẫu đã dùng, nên đổi mẫu không bao giờ đổi số đã cấp. Chuỗi kết quả là `UNIQUE` trong (sổ, dải). Nhờ vậy một mẫu cấu hình sai — ví dụ sổ reset theo năm mà mẫu thiếu `{year}` — làm giao dịch cấp số **hỏng**, thay vì phát ra một số trùng với năm trước.
- **Kỳ:** tính từ `issued_date` theo múi giờ của tổ chức (A-041).
- **Một sổ hay nhiều sổ** là cấu hình: mỗi `request_type` trỏ tới một `document_register`. Nhiều loại dùng chung một sổ hay mỗi loại một sổ đều không đổi DDL.

## Consequences

**Tích cực**

- Tính đúng của "không có lỗ hổng âm thầm" không phụ thuộc vào hành vi của một đối tượng cơ sở dữ liệu chưa được xác minh trong `docs/reference/`.
- Thêm sổ mới hay sang kỳ mới là thêm dòng, không cần DDL — khớp AC của F6 và khớp nguyên tắc role ứng dụng không sở hữu schema (mục Audit log bất biến của `04-data.md`).

**Tiêu cực và cái phải chấp nhận**

- Mọi lệnh phát hành trên cùng (sổ, dải, kỳ) được tuần tự hoá tại một dòng. Chấp nhận được vì giao dịch ngắn, và nhịp phát hành gắn với thao tác của người thật (A-002).
- `VOIDED` làm dãy số có lỗ. Đây là hệ quả chủ đích của việc ưu tiên giải trình hơn liên tục.

**Điều kiện đảo ngược** — tín hiệu vận hành, đo ở `observability`: thời gian chờ khoá trên dòng `document_register_counter`. Chỗ quan sát này **chưa có** trong bảng chỗ quan sát của Phase 11 ở `_PLAN.md` — đã ghi ở Open Questions của `04-data.md`.

## Rejected alternatives

**A — Sequence.** Bị loại vì hai lý do độc lập:

1. Mỗi (sổ, dải, kỳ) cần một sequence riêng, nên thêm sổ hoặc sang năm mới đòi **DDL lúc chạy**. Điều đó trái AC của F6 (thêm loại yêu cầu không sửa code, không deploy lại) và trái nguyên tắc role ứng dụng không sở hữu schema.
2. Muốn biết sequence có để lại lỗ hổng âm thầm hay không thì phải dựa vào hành vi giao dịch của nó — `[CẦN XÁC MINH]` theo tài liệu PostgreSQL, bản gốc chưa có trong `docs/reference/`. Phương án B đúng mà không cần biết điều đó.

**C — `MAX(seq) + 1`.** Bị loại vì dưới đồng thời hai giao dịch đọc cùng một `MAX`, một bên đụng `UNIQUE` và phải thử lại. Số lần thử không có trần đúng lúc tải dồn. Thêm vào đó, `MAX` phải tính cả dòng `VOIDED`, tức một truy vấn tổng hợp nằm trên đường cấp số. B biến va chạm thành chờ khoá có thứ tự.

**Cấp số sớm hơn `ISSUED`** — ở `DRAFT` hay `APPROVED`. Đã bị domain loại (mục Cấp số văn bản của `00-domain.md`); ghi lại để không ai dựng lại.
