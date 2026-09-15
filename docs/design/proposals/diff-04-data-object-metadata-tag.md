# Đề xuất diff — `04-data.md`, mục Lưu trữ file và bất biến bản render

**Trạng thái:** Chờ duyệt · **Nguồn:** mục Backup & Restore của `11-ops.md` (5.2(b)) · **Không tự áp** — `04-data.md` là phase đã đóng (☑ ở `_PLAN.md`)

---

## Vì sao cần

Đối soát sau khôi phục (mục Backup & Restore của `11-ops.md`) cần phân biệt object nào trong `object_storage` là bản **ghim `ISSUED`** so với các bản nháp tích luỹ dưới cùng `document_id`. Khoá object hiện tại (`renders/{document_id}/{input_hash}`) không mang thông tin đó — không đối soát được nếu không đổi giao thức ghi.

## Diff đề xuất

Thêm object metadata (tính năng chuẩn của S3-compatible storage, tách khỏi khoá và khỏi byte nội dung) tại bước ghim `finalize_issue` (giao dịch cuối, cùng lúc chuyển `document` sang `ISSUED`):

| Trường metadata | Giá trị | Điều kiện |
|---|---|---|
| `x-bo19-pin-reason` | `ISSUED` | **Chỉ** gắn ở bước ghim bản cuối — không gắn cho bản `DRAFT`/bản nháp tích luỹ |
| `x-bo19-document-number` | `document_register_entry.formatted_number` | Không phải PII — số hành chính công khai, in ngay trên chính văn bản |

**Bốn điều kiện bắt buộc, không thương lượng khi áp:**

1. **Chỉ gắn cho bản ghim `ISSUED`.** Bản ghim `APPROVED_CONTENT` (ghim ở `document_approve_content`, trước khi có số) và mọi bản nháp — không gắn gì.
2. **Chỉ hai trường trên, không gì khác.** Không PII, không giá trị slot, không nội dung tự do — cùng luật với `audit_event`/`llm_usage`.
3. **`postgresql` vẫn là nguồn sự thật duy nhất.** Tag chỉ đọc lúc đối soát sau khôi phục (thảm hoạ) — **không** đường truy vấn nào ở code đường-nóng (`stored_file_fetch`, `docx_render`, `render_integrity_check`, ...) được đọc metadata này để quyết định nghiệp vụ.
4. **Giới hạn phải nói thẳng:** tag chỉ tồn tại trên object ghi **sau** khi thay đổi này triển khai — không phủ ngược các văn bản đã phát hành trước đó. Đối soát có một ngày bắt đầu, không phải một cơ chế toàn diện.

## Chỗ cần sửa trong `04-data.md` khi áp

- Mục Lưu trữ file và bất biến bản render (5.1): thêm một gạch đầu dòng mô tả metadata ở bước ghim `ISSUED`.
- Mục Giao thức ghi một lần: nói rõ metadata được set trong **cùng** lệnh `PUT`/commit, không phải một lệnh riêng (tránh cửa sổ race giữa ghi object và gắn tag).
- `CHANGELOG.md`: ghi nhận đây là sửa theo quyết định của PO (đề xuất từ Phase 11, áp vào Phase 4), không phải "Phase 4 tự phát hiện sai".

## Đánh đổi cần cân nhắc trước khi duyệt

- Đây là **một lời hứa của tầng ứng dụng với chính nó** (không có gì trong S3-compatible storage buộc metadata phải nhất quán với nội dung DB) — nếu logic ghi có bug, tag có thể sai mà không ai biết cho tới khi cần đối soát thật.
- Không giải quyết được các văn bản đã phát hành trước khi diff này được áp (điều kiện 4).
