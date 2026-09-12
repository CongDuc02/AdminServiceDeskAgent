# ADR-004 — `queue_worker` dùng bảng job trong PostgreSQL, không thêm Redis/Celery

**Trạng thái:** Accepted · **Ngày:** 2026-09-12 · **Quyết định tại:** Phase 2 — System Architecture · **Liên quan:** D-010 (`00-domain.md`), mục Tech stack của `CLAUDE.md`

---

## Context

`queue_worker` phải phục vụ nhiều loại job nền: render `document` sau khi `request` chuyển `SUBMITTED` (D-010), quét `NEEDS_INFO → EXPIRED`, quét SLA/escalation, giải phóng `room_booking` `HELD` quá hạn, gửi notification, tổng hợp chi phí.

Ràng buộc quan trọng nhất tới từ D-010: `document` phải được **render tại đúng thời điểm** `request` chuyển sang `SUBMITTED` — không sớm hơn, không hoãn tới khi có người mở hàng đợi. Cách duy nhất để "tại đúng thời điểm" có nghĩa chắc chắn là: việc **enqueue job render phải nằm trong cùng giao dịch DB** với việc ghi `request.status = SUBMITTED`. Nếu giao dịch chuyển trạng thái thành công mà việc enqueue thất bại (hoặc ngược lại), `request` sẽ ở `SUBMITTED` mà không bao giờ có `document` nào được tạo — đúng lỗ hổng D-010 được viết ra để tránh.

`queue_worker` không nằm trong danh sách công nghệ bắt buộc của `CLAUDE.md` như một hệ thống hàng đợi cụ thể — cần ADR có phương án bị loại.

## Options

**A — Redis + một job queue framework** (kiểu Celery/RQ), chạy như managed service riêng.

**B — Bảng job trong chính PostgreSQL** (mẫu `SKIP LOCKED`), `queue_worker` chạy như Render Background Worker polling định kỳ, cộng Render Cron Job cho các job định kỳ thuần tuý.

## Decision

**Chọn B.**

- Enqueue một job là một câu `INSERT` vào bảng job, chạy **trong cùng transaction SQL** với việc chuyển `request.status = SUBMITTED`. Hai việc thành công hoặc thất bại cùng nhau — không có trạng thái lưng chừng.
- `queue_worker` (Render Background Worker) poll bảng job bằng `SELECT ... FOR UPDATE SKIP LOCKED`, xử lý, đánh dấu hoàn tất hoặc thất bại.
- Các job thuần định kỳ (quét `EXPIRED`, quét SLA, giải phóng `HELD` quá hạn) chạy qua Render Cron Job, không cần vòng lặp poll liên tục.

## Consequences

**Tích cực**

- D-010 được thoả mãn đúng nghĩa đen: enqueue và transition là một hành động nguyên tử duy nhất trên một hệ quản trị dữ liệu.
- Không thêm managed service ngoài PostgreSQL đã có sẵn — không hoá đơn Redis, không thêm bề mặt vận hành.
- Toàn bộ trạng thái job (kể cả lịch sử thất bại, dùng cho A-022 — trần số lần render) nằm cùng chỗ với dữ liệu nghiệp vụ, dễ truy vấn chéo cho audit và cho Phase 11 định cỡ chi phí.

**Tiêu cực và cái phải chấp nhận**

- Polling định kỳ có độ trễ dispatch tối thiểu bằng chu kỳ poll, không phải tức thời như pub/sub.
- Nhiều worker cùng poll một bảng có thể tranh khoá dòng (lock contention) nếu số lượng job và số worker đều lớn.

**Điều kiện đảo ngược quyết định này** — chưa có số liệu tải thật (A-002) nên không đặt ngưỡng số, mô tả hình dạng tín hiệu:

- Lock contention trên bảng job đủ lớn để làm chậm thấy được các giao dịch OLTP khác đang dùng cùng instance PostgreSQL.
- Cần độ trễ dispatch cận-thời-gian-thực (job phải chạy gần như ngay khi enqueue, không chấp nhận được độ trễ bằng một chu kỳ poll) cho một loại job nào đó chưa xuất hiện ở Sprint đầu.
- Thông lượng job đủ lớn để vòng lặp `poll + SKIP LOCKED` tự nó trở thành một tải IO đáng kể cạnh tranh với tải giao dịch chính — cùng loại tín hiệu như ở ADR-002, khác chỗ nó là tải job thay vì tải truy vấn vector.

## Rejected alternatives

**Option A — Redis + Celery/RQ.** Bị loại vì một lý do cụ thể hơn "thêm một hệ thống phải vận hành": nó **phá vỡ tính nguyên tử của D-010**. Ghi vào Postgres (transition) và publish vào Redis (enqueue) là hai hệ thống khác nhau — không có giao dịch chung giữa chúng. Muốn giữ đúng ngữ nghĩa "cùng lúc" thì phải tự dựng thêm một outbox pattern (ghi ý định enqueue vào Postgres trước, một tiến trình khác đọc outbox rồi mới publish sang Redis) — tức là thêm hẳn một tầng phức tạp mới chỉ để tái tạo lại đúng thứ mà bảng job trong Postgres đã có sẵn miễn phí. Chi phí vận hành Redis chỉ là lý do phụ; lý do chính là nó giải quyết sai bài toán.
