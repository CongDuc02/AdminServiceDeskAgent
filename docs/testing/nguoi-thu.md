# Hướng dẫn cho người thử — BO-19, giai đoạn build

**Áp dụng:** từ Sprint 1 tới trước mốc 2 của ADR-032 — tức trước lần đầu dữ liệu nhân viên thật được phép vào hệ thống. **Cập nhật:** 2026-10-02.

---

## 1. Luật duy nhất không có ngoại lệ: **không nhập dữ liệu thật**

Không gõ vào ô chat, không tải lên, không dán vào bất kỳ ô nào:

- họ tên, mã nhân viên, ngày sinh, số căn cước của **người thật**;
- tên cơ quan nhận văn bản, mục đích xin giấy **của một việc có thật**;
- bất cứ thứ gì bạn sẽ không muốn đọc lại trên màn hình của người khác.

Chỉ dùng **tài khoản giả** được cấp và **nội dung bịa**. Ví dụ dùng được: "Xin giấy xác nhận công tác để nộp hồ sơ vay tại Ngân hàng Thử Nghiệm ABC, 2 bản". Cố đặt tên sao cho ai đọc cũng nhận ra là giả.

**Vì sao.** Mỗi tin nhắn chat được gửi nguyên văn tới nhà cung cấp mô hình ngôn ngữ — trong giai đoạn này là Groq, xử lý và lưu ở Mỹ (`docs/reference/llm-groq.md`). Thủ tục chuyển dữ liệu cá nhân ra nước ngoài theo Luật Bảo vệ dữ liệu cá nhân năm 2025 chưa được xét xong (A-080, ADR-032). Hệ thống không có chặn kỹ thuật nào phân biệt được dữ liệu thật với dữ liệu giả — chỉ có bạn.

**Lỡ nhập dữ liệu thật:** dừng lại, báo ngay người triển khai, kèm thời điểm và tài khoản đã dùng. Đừng tự xoá rồi thôi.

## 2. Hệ thống đang ở chế độ thử nghiệm

- Mọi trang có **dải báo chế độ thử nghiệm**.
- Mọi văn bản sinh ra mang watermark **"BẢN THỬ NGHIỆM — KHÔNG CÓ GIÁ TRỊ PHÁP LÝ"** ngay trong file, và số văn bản lấy từ dải `TRIAL`. Không in, không gửi văn bản thử cho bất kỳ ai như văn bản thật.
- Không có thao tác đóng dấu vật lý nào xảy ra.

## 3. Những điều sẽ gặp

| Điều | Vì sao | Làm gì |
|---|---|---|
| Lần đầu mở trang chờ khoảng một phút | Bản trên Render dùng gói free, ngủ sau 15 phút không ai truy cập (ADR-033) | Chờ; không cần tải lại liên tục |
| Agent trả lời "hệ thống đang bận, thử lại sau" | Nhà cung cấp mô hình giới hạn số token mỗi phút cho **cả hệ thống** — vài lượt chat mỗi phút (`docs/reference/llm-token-count-p1-p2.md`) | Chờ một phút rồi gửi lại |
| Đăng nhập báo đã thử quá nhiều lần | Rate limit đăng nhập (`docs/design/09-security.md`) | Chờ hết cửa sổ rồi thử lại |
| Yêu cầu, văn bản thử biến mất sau vài tuần | Cơ sở dữ liệu free được dựng lại theo chu kỳ dưới 30 ngày (`docs/design/11-ops.md`, runbook dựng lại PostgreSQL free) | Không làm gì — đó là dữ liệu giả. Người triển khai báo trước mỗi lần dựng lại |
| Báo lỗi có kèm mã `trace_id` | Mã truy vết của request | Chép nguyên mã khi báo lỗi |

## 4. Báo lỗi

Gửi cho người triển khai: bạn đã làm gì, thấy gì, mong thấy gì, thời điểm, tài khoản thử, và `trace_id` nếu có. Chụp màn hình được thì tốt — miễn là trên màn hình chỉ có dữ liệu giả.
