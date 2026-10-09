# Đề xuất — nơi lưu và cách lắp khuôn trả lời của `intake_graph` (`reply_template_id`)

**Trạng thái:** ✅ **PO duyệt 2026-10-09** — R1–R6 theo mặc định; PO sửa câu chữ trước UAT. Phần mã khuôn thuộc **B6b**; B6a chỉ thêm cột `label_vi` (S1) và `status_labels` (S2). · **Ngày:** 2026-10-09 · **Người đề xuất:** người triển khai (Claude) · **Đã đọc:** `03-agents.md` (mục `intake_agent`, mục State schema, mục `intake_graph`), `08-hitl.md`, `04-data.md` (mục `chat_message`), `05-api.md` (mục SSE, `ChatMessage`), `07-prompts.md`, `openapi.yaml`

## 1. Thiết kế đã chốt gì — và còn thiếu gì

**Đã chốt:**

- Không có văn bản tự do từ LLM hiển thị cho nhân viên (ADR-007): *"Câu trả lời trong chat do `render_reply` lắp từ khuôn"* (`03-agents.md`, `intake_agent`). `render_reply` là node tất định, không LLM.
- `PendingQuestion.template_id` là *"id khuôn câu trong cấu hình, không phải văn bản câu"* (State schema); `IntakeState.reply_template_id` là mã.
- `chat_message.reply_template_id` chỉ có ở tin của agent. **`chat_message.body` vẫn bắt buộc không `NULL`** (`ck_chat_message_body_until_erased`) và là `RES` — tức bản đã lắp được lưu, cạnh mã khuôn. Lý do: bản có thẩm quyền khi stream đứt là dòng `chat_message` (`05-api.md`, mục SSE); `GET …/messages` phải trả đủ nội dung.
- Nhánh lỗi ghi *đúng một* dòng `chat_message` của agent mang mã khuôn lỗi ("hệ thống đang bận"); chạm trần token thì khuôn chuyển liên hệ phòng hành chính; hỏi làm rõ quá ngưỡng thì khuôn liên hệ phòng hành chính; dòng 7 của bảng ánh xạ P1 có khuôn riêng nêu tên loại chưa hỗ trợ và liệt kê mọi loại đang hỗ trợ.
- Thông báo (`notification`) dùng cơ chế **khác**: câu hiển thị là khuôn theo `event_code` ở `client` (`08-hitl.md`). Đề xuất này không đụng tới.

**Chưa chốt (hai chỗ trống):**

1. **Văn bản khuôn nằm ở đâu, tham số nào được vào.** "Cấu hình" không được định nghĩa. Không bảng, không file, không module nào được đặt tên.
2. **Nhãn tiếng Việt của slot** ("mục đích", "nơi nhận"). `ASK_SLOT` cần nêu slot còn thiếu bằng chữ người dùng đọc được. `slot_definition` chỉ có `slot_name` (mã) và `description` (**đầu vào của P2**, viết cho LLM — `04-data.md`); `request_type` có `name_vi` nhưng slot thì không. Màn hình xác nhận từng slot của client (`/my-requests/:requestId`) cần cùng nhãn đó.

(Ghi chú liên quan: `05-api.md` đòi `status_label` tiếng Việt "từ **một** danh mục phía server" — danh mục đó cũng chưa có nơi. `resume_context` cần nó. Xem S1 dưới.)

## 2. Yêu cầu đặt ra cho nơi lưu

1. PO và phòng hành chính **đọc và sửa được câu chữ** mà không cần đọc Python.
2. Tất định, không LLM; tham số **đóng và có kiểu** — khuôn không bao giờ nhận văn bản tự do (nhân viên gõ hay LLM sinh) làm tham số, nên không thể lọt PII hay chỉ thị vào câu trả lời.
3. Fail-closed: thiếu tham số, thừa tham số, hay khuôn lạ → lỗi, không đoán.
4. F6: *thêm `request_type` không đòi sửa code* → tên loại và nhãn slot lấy từ cấu hình DB, không chép vào file khuôn.
5. Đổi câu chữ không làm đổi mã khuôn; tin cũ giữ nguyên `body` đã lắp (mã khuôn chỉ để truy vết).
6. Không i18n (ngoài phạm vi).

## 3. Phương án

| | Phương án | Được | Mất |
|---|---|---|---|
| **A** | **File JSON trong repo, cạnh module** — `orchestrator/intake_graph/reply_templates.json` + `reply_templates.py` (nạp, kiểm, lắp) | PO đọc/sửa được; có schema; git là lịch sử; không migration; cùng khuôn `model_profiles.json` (B4b) | Đổi câu chữ = phát hành mã; chưa có màn hình sửa |
| B | Hằng số trong module Python (mặc định PO nêu) | Có kiểu, import-time | Câu chữ lẫn trong mã; PO khó đọc; cùng chi phí phát hành như A mà không có lợi gì thêm |
| C | Bảng DB `reply_template` + data migration | Sửa không cần phát hành; hợp F6 | Cần migration + màn hình (Sprint 3) + data migration lên cả Render; thêm bề mặt lỗi lúc chạy; chưa có người dùng nào cần sửa |
| D | Ở `client` như thông báo | Giống thông báo | Server phải lưu `body` đã lắp (RES) → server phải biết câu chữ; bị loại |

**Đề xuất: A.** Nó là B có thêm khả năng PO đọc và kiểm tự động; chuyển lên C sau này là cơ học vì mã khuôn ổn định (điều kiện đảo ngược: có yêu cầu sửa câu chữ không qua phát hành, hoặc F6 đòi khuôn riêng theo loại).

## 4. Hình dạng đề xuất (A)

```json
{
  "schema_version": 1,
  "templates": {
    "ASK_SLOT": {
      "text": "Để làm {type_name}, mình cần thêm: {slot_labels}. Bạn cho mình biết nhé.",
      "params": {"type_name": "TYPE_NAME", "slot_labels": "SLOT_LABELS"}
    }
  }
}
```

- **Kiểu tham số — danh sách đóng**, không có kiểu "chuỗi bất kỳ": `TYPE_NAME` (một `request_type.name_vi`), `TYPE_NAMES` (danh sách `name_vi`), `SLOT_LABELS` (danh sách nhãn slot), `STATUS_LABEL` (một nhãn trạng thái). Mọi giá trị đến từ **cấu hình DB hoặc danh mục trạng thái**, không từ nhân viên, không từ LLM. Danh sách lắp bằng dấu phẩy và "và" cuối.
- **Không khuôn nào trong B6 nhận giá trị slot.** Bản tóm tắt `offer_submit` nêu *nhãn* slot đã đủ và dẫn nhân viên tới màn hình yêu cầu để xem từng giá trị (nơi hiển thị theo `slot_sensitivity`, `RES` ẩn mặc định) — `body` của chat (`RES`) không phải nơi lặp lại giá trị `PER`/`RES`. Đây là chỗ lệch nhẹ so với chữ "tóm tắt" ở sơ đồ `intake_graph`; nếu PO muốn tóm tắt kèm giá trị trong chat, đó là một kiểu tham số mới (`SLOT_VALUES`, mang độ nhạy) và mask log phải theo.
- **Kiểm** (`reply_templates.py`): `{tên}` trong `text` khớp đúng tập `params`; kiểu thuộc danh sách đóng; mã khuôn khớp `^[A-Z][A-Z0-9_]*$`; mã dùng bởi `PendingQuestion.kind`, `route_intent` và nhánh lỗi **đều có khuôn** (test cắt chéo, thiếu một mã là đỏ); không `{`/`}` lạ; độ dài ≤ 600 ký tự.
- **Lắp:** `render(template_id, params) -> (text, template_id)`; thiếu hay thừa tham số, kiểu sai, danh sách rỗng ở khuôn đòi danh sách → `ReplyTemplateError` (mã), node `render_reply` bắt ở biên node và trả khuôn lỗi cứng — không bao giờ để lộ lỗi cho nhân viên.
- **Nạp:** một lần, khi dựng graph. Kiểm lúc khởi động: **thêm bước kiểm #25 "file khuôn hợp lệ"** vào bảng ở `06-structure.md` (cùng khuôn #21 hồ sơ model: `api` không khởi động với file khuôn hỏng) — nếu PO không muốn thêm bước, mặc định lùi về kiểm bằng test và kiểm lần đầu dùng.

## 5. Kho khuôn cho B6 (bản nháp câu chữ — **do người triển khai (Claude) soạn, PO duyệt trước UAT**; thêm thành điều kiện ở cổng 4.x)

| Mã khuôn | Dùng ở | Tham số | Bản nháp |
|---|---|---|---|
| `CLARIFY_TYPE` | `ask_clarification`; `PendingQuestion.CLARIFY_TYPE` | `type_names` (có thể rỗng → khuôn thứ hai `CLARIFY_TYPE_NO_CANDIDATE`) | "Bạn muốn làm loại giấy tờ nào: {type_names}? Bạn nói rõ giúp mình nhé." |
| `CLARIFY_TYPE_NO_CANDIDATE` | như trên, khi P1 không trả ứng viên | `type_names` = mọi loại đang hỗ trợ | "Mình chưa hiểu rõ bạn cần giấy tờ nào. Hiện mình hỗ trợ: {type_names}. Bạn cho mình biết thêm nhé." |
| `CLARIFY_LIMIT_REACHED` | quá ngưỡng hỏi làm rõ (A-031) | — | "Mình chưa hiểu rõ yêu cầu của bạn sau vài lần hỏi. Bạn vui lòng liên hệ trực tiếp Phòng Hành chính để được hỗ trợ." |
| `ASK_SLOT` | `ask_missing`; `PendingQuestion.ASK_SLOT` | `type_name`, `slot_labels` | "Để làm {type_name}, mình cần thêm: {slot_labels}. Bạn cho mình biết nhé." |
| `ASK_SLOT_RETRY` | slot bị loại (`EVIDENCE_MISMATCH`, `RULE_FAILED`) | `slot_labels` | "Mình chưa ghi nhận được thông tin cho: {slot_labels}. Bạn nhập lại giúp mình, nêu cụ thể hơn nhé." |
| `ASK_PURPOSE_RETRY` | `purpose` bị loại (`RULE_FAILED` do `min_tokens`/`non_blank`, hoặc `EVIDENCE_MISMATCH`) — thêm theo chỉnh V2 của PO | — | "Mình chưa ghi nhận đủ rõ mục đích. Bạn viết cụ thể hơn một chút nhé, ví dụ: \"bổ sung hồ sơ vay vốn tại ngân hàng\"." |
| `CONFIRM_PROPOSALS` | `propose_values` có đề xuất | `slot_labels` | "Mình đã điền sẵn từ hồ sơ của bạn: {slot_labels}. Bạn mở yêu cầu của mình để kiểm tra và xác nhận từng mục." |
| `OFFER_SUBMIT` | `offer_submit` | `type_name` | "Hồ sơ cho {type_name} đã đủ thông tin. Bạn mở yêu cầu của mình để xem lại và bấm gửi." |
| `OUT_OF_SCOPE_KNOWN` | dòng 7 của bảng ánh xạ P1 | `unsupported_type_name`, `type_names` | "Mình chưa hỗ trợ {unsupported_type_name}. Hiện mình hỗ trợ: {type_names}. Với {unsupported_type_name}, bạn vui lòng liên hệ trực tiếp Phòng Hành chính." |
| `OUT_OF_SCOPE_GENERIC` | dòng 8 + `procedure_store = NOT_READY` (Sprint 1: mọi ngoài phạm vi) | `type_names` | "Yêu cầu này nằm ngoài những gì mình hỗ trợ lúc này (hiện có: {type_names}). Bạn vui lòng liên hệ trực tiếp Phòng Hành chính." |
| `RESUME_STATUS` | `resume_context` | `type_name`, `status_label` | "Yêu cầu {type_name} của bạn hiện ở trạng thái: {status_label}. Nếu bạn cần làm yêu cầu khác, cứ cho mình biết." |
| `ERROR_BUSY` | lỗi gọi model, hết hạn chót lượt | — | "Hệ thống đang bận, bạn thử lại sau một lúc nhé. Tin nhắn của bạn đã được lưu." |
| `BUDGET_LIMIT` | `BUDGET_EXCEEDED` | — | "Phiên trò chuyện này đã đạt giới hạn xử lý. Bạn vui lòng liên hệ trực tiếp Phòng Hành chính." |

13 khuôn (12 của đề xuất đầu + `ASK_PURPOSE_RETRY`). Câu ví dụ trong `ASK_PURPOSE_RETRY` là chữ cố định, không phải tham số. **Không bịa:** không có số điện thoại, thư điện tử hay giờ làm việc của Phòng Hành chính — chưa có trong thiết kế. Khi PO cấp thông tin liên hệ, nó vào khuôn qua một kiểu tham số mới `ADMIN_CONTACT` lấy từ cấu hình; đến lúc đó khuôn chỉ nói "liên hệ trực tiếp Phòng Hành chính". `OFFER_NEXT_INTENT` (EC-CV-01) và `EXPLAIN_TERMINAL` (EC-CV-04, `EXPIRED`) là khuôn của **Sprint 2** — không nằm trong kho B6.

## 6. Hai đề xuất đi kèm

**S1 — Nhãn slot: thêm cột `slot_definition.label_vi`** (`text NOT NULL`, migration `0011`, bảng cấu hình còn trống nên thêm `NOT NULL` không cần giá trị mặc định). Nhãn đi cùng cấu hình DB đúng như `request_type.name_vi` — thêm loại mới không sửa file nào (F6). `description` giữ nguyên là đầu vào P2. Thay thế (đặt nhãn trong file khuôn) bị loại vì nó bắt thêm loại phải sửa mã, đúng điều F6 cấm; và client cần cùng nhãn từ API (`SlotDefinition` hiện không có trường nào). Cần sửa `04-data.md` (mục Cấu hình loại yêu cầu), `contracts/README.md`, `openapi.yaml` nếu `RequestDetail` trả nhãn.

**S2 — Danh mục `status_label`:** hằng số trong `bo19.domain` (mười trạng thái `request`; `document` khi có vòng đời), một nơi, cả `api` và `orchestrator` import được (tầng `domain` thấp nhất). Đóng chỗ trống "một danh mục phía server" của `05-api.md`.

## Quyết định cần PO

| # | Quyết định | Mặc định |
|---|---|---|
| R1 | Nơi lưu khuôn: A (JSON cạnh module) / B (Python) / C (DB) | **A** |
| R2 | Thêm bước kiểm khởi động #25 "file khuôn hợp lệ" | Thêm |
| R3 | `offer_submit` chỉ nêu nhãn, không lặp giá trị slot trong chat | Đồng ý |
| R4 | Nhãn slot: cột `label_vi` (migration `0011`) / trong file khuôn | **Cột `label_vi`** |
| R5 | `status_label`: hằng số ở `bo19.domain` | Đồng ý |
| R6 | Kho 12 khuôn và bản nháp câu chữ ở mục 5 | PO sửa chữ khi duyệt hoặc trước UAT |

## Open Questions

- Thông tin liên hệ của Phòng Hành chính (đầu mối, giờ làm việc) — chưa có trong thiết kế; khuôn dùng "liên hệ trực tiếp Phòng Hành chính" tới khi có.
