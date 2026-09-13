# ADR-016 — Lượt chat chạy ở một task riêng, không gắn với vòng đời kết nối

**Trạng thái:** Accepted · **Ngày:** 2026-09-13 · **Quyết định tại:** Phase 6 — Project Structure · **Liên quan:** ADR-005, ADR-013, NFR-04, NFR-06, NFR-08 của `01-prd.md`, A-025, A-031, A-051, A-056, mục SSE của `05-api.md` · **Nguồn:** `docs/reference/starlette-streaming-disconnect.md`, `docs/reference/render-deploys-docker.md`

---

## Context

Mục SSE của `05-api.md` chốt: **lượt không bị huỷ khi client ngắt kết nối** — server chạy lượt tới cuối và ghi đúng một tin nhắn của agent. Bản có thẩm quyền là dòng `chat_message`, không phải stream. `05-api.md` giao cho Phase 6 bảo đảm điều này, và ghi A-051(4) — framework có huỷ xử lý khi client ngắt hay không — là `[CẦN XÁC MINH]`.

Nguồn đã ghim của Starlette 1.6.0 trả lời ở mức đủ để quyết: với `StreamingResponse`, khi client ngắt, **việc chạy bên trong body iterator không tiếp tục**. Máy chủ ASGI báo `spec_version` dưới 2.4 thì tác vụ stream bị huỷ qua `cancel_scope`. Từ 2.4 trở lên thì lần `send` hỏng được đổi thành `ClientDisconnect`, và iterator không được lặp tiếp.

Vì vậy, chạy `intake_graph` **bên trong** generator của response là sai theo đúng contract của `05-api.md`.

## Options

- **A — Task riêng trong tiến trình `api`**, do một bộ giám sát lượt quản lý. Response stream chỉ chuyển tiếp sự kiện của task qua một kênh trong bộ nhớ.
- **B — Chạy trong body iterator, che nó khỏi bị huỷ.**
- **C — Enqueue lượt chat vào `queue_worker`** — điều kiện đảo ngược của ADR-005.
- **D — `BackgroundTask` của Starlette.**

## Decision

**Chọn A.**

- Handler của `POST /chat-sessions/{id}/turns` làm theo thứ tự:
  1. ghi tin nhắn của nhân viên qua `chat_message_append` và commit;
  2. đăng ký một task lượt với bộ giám sát lượt của tiến trình — task **không** thuộc phạm vi của request;
  3. trả response stream. Iterator của stream chỉ đọc kênh sự kiện của lượt đó (`turn.accepted`, `turn.progress`, `turn.reply`, `turn.error`).
- Client ngắt thì iterator dừng, task **chạy tiếp**. Task luôn kết thúc bằng đúng một tin nhắn của agent — thành công, hoặc mang mã khuôn lỗi — qua `chat_message_append`. Không còn ai nghe thì kênh bị bỏ.
- **Hạn chót của lượt do chính task thi hành** (giá trị ở A-031). Quá hạn thì task huỷ lượt chạy graph và ghi tin nhắn agent mang mã khuôn lỗi. Huỷ giữa chừng đi qua lớp chặn exception ở biên node của `orchestrator` (mục Cây backend của `06-structure.md`), vì LangGraph lưu exception của task bị huỷ vào checkpoint (`docs/reference/langgraph-checkpoint-postgres.md`).
- **"Một lượt tại một thời điểm cho mỗi phiên" đọc từ DB, không đọc từ bộ giám sát.** Tin nhắn nhân viên cuối cùng chưa có câu trả lời, còn trong hạn chót, thì trả `TURN_IN_PROGRESS`. Bộ giám sát chỉ biết task của chính tiến trình nó; có nhiều instance thì chỉ DB mới đúng.

## Consequences

**Giá trị chính:** hệ thống đúng **bất kể** A-051(4) trả lời thế nào. Framework huỷ hay không huỷ xử lý khi client ngắt không còn đổi được hành vi của lượt, vì lượt không còn chạy ở chỗ có thể bị huỷ. **Vì vậy không dựng test ngắt kết nối để xác minh A-051(4)** — bỏ công vào đó là tiêu tiền cho một câu hỏi đã hết quan trọng. A-051(4) chỉ được thu hẹp bằng tài liệu.

**Ba hệ quả phải thiết kế, không để rơi:**

1. **Lượt sống lâu hơn request.** Giới hạn thời gian request của Render (A-025) không còn chặn lượt: nó chỉ cắt stream, và client dựng lại lượt bằng `GET /chat-sessions/{id}/messages`. Hạn chót do task tự thi hành là **thứ duy nhất còn bảo đảm lượt kết thúc**. Không có nó thì một lời gọi model treo giữ task mãi mãi.
2. **Tắt tiến trình êm (SIGTERM) là việc của entrypoint, không phải của Phase 11.** Theo nguồn đã ghim của Render: khi deploy, instance mới nhận toàn bộ traffic, 60 giây sau instance cũ nhận `SIGTERM`, rồi `SIGKILL` sau shutdown delay — mặc định 30 giây, tối đa 300 giây. Không có cửa sổ drain thì mọi lượt đang chạy bị giết, tức **A-056 xảy ra ở mỗi lần deploy**, không còn là ca hiếm. Entrypoint `api` vì vậy, khi nhận `SIGTERM`:
   - ngừng nhận kết nối mới;
   - đóng mọi stream tín hiệu ngay — client nối lại sang instance mới (ADR-013);
   - chờ các task lượt đang chạy xong;
   - tới hạn drain thì huỷ task còn lại và cố ghi tin nhắn agent mang mã khuôn lỗi cho từng task, với timeout ngắn;
   - thoát mã 0.

   **Ràng buộc cấu hình:** hạn chót của lượt, cộng biên an toàn, **không được dài hơn** shutdown delay đã cấu hình. Như vậy mọi lượt bắt đầu trước `SIGTERM` đều kết thúc tự nhiên trong cửa sổ drain. Bước kiểm khởi động của `api` từ chối khởi động nếu cấu hình vi phạm ràng buộc này. Entrypoint `worker` làm việc tương đương với job đang chạy: ngừng nhận job mới, hoàn tất hoặc trả job về hàng đợi trong shutdown delay — đúng hành động mà nguồn của Render gợi ý.
3. **A-056 được thu hẹp, không được đóng.** Instance vẫn có thể bị thay mà không kịp drain; tiến trình vẫn có thể chết vì hết bộ nhớ hay bị giết. Khi đó tin nhắn của nhân viên vẫn không có câu trả lời, và không có điểm dừng nào có tên. A-056 giữ nguyên trạng thái cho Phase 8.

**Tiêu cực và cái phải chấp nhận**

- Task lượt chiếm tài nguyên của tiến trình `api` sau khi client đã đi. Số task đồng thời bị chặn trên bởi số phiên đang chat, vì mỗi phiên chỉ có một lượt tại một thời điểm.
- Stream bị cắt thì client không nhận `turn.progress`; nó phải dựng lại lượt bằng GET. Đúng như contract của `05-api.md` đã chấp nhận.

**Điều kiện đảo ngược** — tín hiệu vận hành, dùng lại chỗ quan sát của ADR-005: phân phối thời lượng một lượt chạy `orchestrator` trong tiến trình `api`, nhìn phần đuôi. Khi phần đuôi tiến sát shutdown delay tối đa, drain không còn phủ được lượt. Khi đó chuyển sang phương án C.

## Rejected alternatives

**B — Che body iterator khỏi bị huỷ.** Loại vì hành vi phụ thuộc nhánh `spec_version` của máy chủ ASGI — nguồn cho thấy hai nhánh dừng iterator bằng hai cơ chế khác nhau. Với nhánh từ 2.4, iterator không bị huỷ mà đơn giản là **không được lặp tiếp**, nên không có gì để "che". Một thiết kế đúng hay sai tuỳ phiên bản máy chủ là thiết kế chưa xong.

**C — Enqueue lượt vào `queue_worker`.** Không sai, và là đường đảo ngược mà ADR-005 đã để sẵn. Loại cho hôm nay vì mọi lượt chat sẽ chịu thêm một chu kỳ poll (ADR-004), và tiến độ phải được lưu xuống DB mới tới được client — trong khi chưa có số đo nào cho thấy lượt chat tiến sát giới hạn.

**D — `BackgroundTask` của Starlette.** Loại vì hai lý do có trong nguồn: background task chạy **sau** khi stream kết thúc, nên không phát được tiến độ; và ở nhánh `spec_version` từ 2.4, `ClientDisconnect` được ném ra trước dòng gọi background — lượt sẽ không chạy đúng lúc nó cần chạy.
