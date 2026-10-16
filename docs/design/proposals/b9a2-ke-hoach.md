# Kế hoạch B9a2 — `combined_main` và đo O1-6

**Trạng thái:** đề xuất, chờ PO duyệt · **Ngày:** 2026-10-16 · **Căn cứ:** ADR-033 (mục Render free), O1-6 và A-095 (`12-roadmap.md`, `ASSUMPTIONS.md`), bước kiểm #18 (`06-structure.md`) · **Migration:** không · **Biến môi trường mới:** không

## Mục tiêu

Dựng entrypoint `python -m bo19.entrypoints.combined_main` — `api` và vòng poll job của `worker` trong **một** tiến trình — rồi đo trong container giả lập Render free (`--memory=512m --cpus=0.1`) xem nó có giữ được bất biến của S4 và hạn chót lượt WV-02 khi `soffice` đang chuyển đổi. Chưa đổi Start Command của Render: việc đó là của PO sau khi duyệt số đo.

## Làm gì

1. **`combined_main`** — chỉ ghép hàm khởi chạy sẵn có của `api_main` và `worker_main`, không logic nghiệp vụ mới (ADR-033).
   - Bước kiểm khởi động chạy **hợp** mọi bước có ✔ ở bất kỳ cột nào, cộng #18 (`Entry.COMBINED` đã có trong `startup.model`).
   - Vòng poll chạy ở luồng riêng, **một job một lúc**; `soffice` tối đa **một** lần chuyển đổi một lúc (ADR-033, A-031).
   - Tắt êm trong cùng `BO19_SHUTDOWN_DELAY_SECONDS`: uvicorn drain lượt chat **và** worker trả job chưa xong về hàng đợi; log `SIGTERM_RECEIVED` / `PROCESS_EXIT` như `api_main` (O1-5).
2. **Bước kiểm #18** — `BO19_ENVIRONMENT = dev`, nếu không thì Chặn `STARTUP_18_COMBINED_ONLY_IN_DEV`; có code trong `registry`, bỏ khỏi `DECLARED_PENDING`.
3. **Test** (tiến trình thật, như `test_entrypoints_shutdown`): khởi động và phục vụ `/healthz`; một job `render_document` do vòng poll trong cùng tiến trình xử lý tới `PENDING_APPROVAL` (provider LLM giả); `SIGTERM` khi vừa có lượt chat vừa có job — cả hai kết thúc đúng; `staging` và `prod` bị #18 chặn mà không giành job nào; thiếu `BO19_RENDER_FINGERPRINT_KEY` bị #24 chặn (hợp các cột).
4. **Đo O1-6 và A-095** trên image thật, container `--memory=512m --cpus=0.1`, provider LLM giả có độ trễ cố định (không gọi Groq):
   - bộ nhân chứng `tools/render-probes/s4_witness_poll.py` với `combined_main`: drain và hành vi `SIGTERM`, so với số S4 (≈ 5 s);
   - **một lượt chat giả trong lúc `soffice` chuyển đổi**, so với hạn chót lượt WV-02 (20 s) và biên WV-03 (10 s) — số đo B8b: một chuyển đổi mất 32–88 s ở 0,1 CPU;
   - RSS theo thời gian dưới tải hỗn hợp (đăng nhập, chat, một chuyển đổi, một tải file) so với 512 MiB;
   - ghi kết quả vào `docs/reference/` kèm lệnh chạy lại, và cập nhật O1-6, A-095, ADR-033 (mục Cập nhật).
5. **Tài liệu trước code**: `06-structure.md` (mục Tiến trình và Triển khai ở B9a2), `11-ops.md` (Start Command cho Render), `CHANGELOG.md`.

## Không làm

- **Bộ hẹn giờ cron.** `cron_main` và mọi thao tác cron chưa có code; bộ hẹn giờ không có gì để gọi. `cron_scheduler_main` và phần hẹn giờ của `combined_main` đi cùng thao tác cron đầu tiên (Sprint 2).
- Đổi `CMD` của `Dockerfile` (giữ `api_main`) hay đổi Start Command trên Render.
- Gọi Groq thật. `/tmp` của Render là đĩa hay RAM: chỉ đo được trên Render thật (A-095, PO đồng ý kiểm ở cổng 2.x đầu tiên có Render).

## Câu cần PO quyết (mặc định in đậm)

1. **Bộ hẹn giờ cron:** để sang lát có thao tác cron đầu tiên (**mặc định**), hay dựng khung rỗng ngay?
2. **Nếu số đo vi phạm** (lượt chat vượt WV-02 + WV-03 khi `soffice` chạy): **dừng và báo cùng phương án** (ví dụ `nice`/ưu tiên thấp cho `soffice`, hạ trần một chuyển đổi, hoặc quay về "Render free chỉ chạy `api_main`" theo điều kiện đảo ngược của ADR-033), không tự chọn.
3. **Độ trễ của provider giả** khi đo lượt chat: **2 s** (mức đo Groq thật của B9a: 1,5–2,9 s cho P4; thời lượng P1 + P2 của một lượt chat ghi ở mục Điều kiện trước AC-1.1 của `11-ops.md`) — nêu nếu muốn con số khác.

## Điều kiện xong

Test mới đạt; CI xanh; mutation: bỏ #18, bỏ giới hạn một job, bỏ drain của vòng poll, đổi `combined_main` sang bỏ #24 — mỗi mẫu đỏ; báo cáo số đo kèm lệnh; O1-6 và A-095 cập nhật; PO duyệt trước khi chuyển Start Command.

---

## Kết quả (2026-10-16)

PO duyệt 2026-10-16 (cron để sau; vi phạm hạn chót thì dừng; provider giả 2 s; thêm: `SIGTERM` giữa chuyển đổi giết `soffice`, release, thoát ≈ 5 s, không mồ côi/zombie). Làm xong: mục Triển khai ở B9a2 của `06-structure.md`; số đo `docs/reference/combined-main-b9a2.md`. **Không vi phạm hạn chót lượt và không vượt 5 s** nên không phải dừng. Hai phát hiện ngoài kế hoạch, đã xử lý trong cùng lát: Python PID 1 để lại zombie sau mỗi chuyển đổi (bộ dọn `observability.reaper`) và thoát mềm ở 0,1 CPU mất ≈ 10 s (thoát cứng).
