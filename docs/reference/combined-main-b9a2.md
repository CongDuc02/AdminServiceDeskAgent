# `combined_main` trong cgroup của Render free — số đo B9a2 (O1-6, A-095)

**Ngày đo:** 2026-10-16 · **Công cụ:** `tools/combined-probe/` (`run_probe.py`, `combined_probe.py`, `pid1_probe.py`) · **Kết quả thô:** `docs/reference/combined-main-b9a2-result.json` (lần đo hợp lệ cuối; chỉ số, mã và giờ — không nội dung).

## Điều kiện — và chúng KHÔNG giống Render ở đâu

- **Image runtime thật** của `Dockerfile` (stage `runtime`), `combined_main` là **PID 1** của container (`python -m bo19.entrypoints.combined_main`), `--cpus=0.1 --memory=512m --memory-swap=512m` (A-095: 512 MB RAM, 0,1 CPU). PostgreSQL 18 (`pg`), SeaweedFS 4.47 (`bo19-s3`) cùng network Docker.
- **Provider LLM là một máy chủ HTTPS GIẢ** (không gọi Groq lần nào), trễ cố định **2 s** mỗi lời gọi (PO 2026-10-16), trả P1 và P2 hợp schema. `combined_main` chạy đúng đường thật tới provider (httpx → TLS → HTTP); `ProviderClient` đặt `trust_env=False` nên chứng chỉ tự ký được thêm vào đúng bộ CA của `certifi` trong container bằng một bind mount (công cụ làm việc đó). Mỗi lượt chat là hai lời gọi (P1 rồi P2) = **4 s trễ giả** trong con số "lượt chat" dưới đây; máy chủ giả ghi nhận 5 lượt × 2 = 10 lời gọi.
- **Mẫu `.docx` giả không có biến nội dung tự do** — job `render_document` đi hết đường thật (graph, tool, `soffice`, object storage) nhưng không gọi LLM.
- **Docker Desktop (WSL2), cgroup v2** — không phải máy của Render. `--cpus=0.1` là hạn mức băm (quota) của cgroup, đúng cơ chế nhưng không chứng minh Render cho đúng 0,1 lõi theo cùng nhịp. Số của Render thật vẫn là việc của cổng 2.x đầu tiên có Render.
- **n nhỏ:** hai lượt nền, ba lượt khi chuyển đổi, một lần `SIGTERM` ở lần đo hợp lệ cuối; các lần đo trước (cùng mã trừ chi tiết ghi ở mục Phát hiện) cho cùng thứ tự độ lớn. Đây là số đo, không phải thống kê.
- **Không đo tải file** (cần bản `FINAL`, B9b): phép tính bộ nhớ của B8c (≈ 2 MiB cho bốn lượt tải) giữ nguyên.

## Kết quả

| Việc đo | Kết quả |
|---|---|
| **A. Lên `/healthz` từ lúc `docker run`** | 41,8 s (tổng 45,1 s). Các lần đo khác 39,8–48,1 s. Import module ở 0,1 CPU là phần lớn — cold start của Render free sẽ còn cộng thời gian kéo image |
| **B. Lượt chat không có chuyển đổi (nền)** | **6,2 s**, **5,5 s** (gồm 4 s trễ giả của P1+P2); đăng nhập 0,7 s và 0,4 s |
| **C. Lượt chat trong lúc `soffice` chuyển đổi** | **12,1 s** và **11,2 s** (`soffice` đang chạy trước và sau lượt); lượt thứ ba **7,7 s** (chuyển đổi đã xong). Đăng nhập 1,1–1,4 s. **Mọi lượt trong hạn chót WV-02 = 20 s** (dư ≥ 7,9 s); so với nền: **+5 đến +6 s** khi `soffice` chạy. `soffice` hiện ra 9,2 s sau khi gửi job |
| **D. `SIGTERM` lúc `soffice` đang chuyển đổi** | `docker kill -s TERM` (như Render): log `SIGTERM_RECEIVED` → **+1,1 s** `JOB_RELEASED_ON_DRAIN` → **+1,6 s** `PROCESS_EXIT` (mã 0); `docker top` thấy tiến trình `soffice` biến mất lúc +1,47 s và container dừng được quan sát lúc **+2,3 s**; nhân chứng `pg_stat_activity` (`s4_witness_poll.py`, 0,25 s): kết nối cuối thấy lúc +1,45 s, **biến mất lúc +1,70 s**. Hạn Render ≈ 5 s (A-031, S4). **Không vượt** |
| **D'. Job sau `SIGTERM`** | `QUEUED`, `attempts = 0` (release không tiêu lượt thử), `document` ở `DRAFT` |
| **D''. Bảng tiến trình lúc thoát** | `PROCESS_TABLE_AT_EXIT`: `children = 0`, `zombies = 0`, `reaped = 5` (năm zombie của lần chuyển đổi trước đã được bộ dọn thu); `docker top` sau `SIGTERM`: chỉ còn `python` rồi trống — **không `soffice` mồ côi, không zombie** |
| **E. Bộ nhớ** (sau B, C; trước D) | đỉnh cgroup **304 MiB** / 512 MiB, `oom_kill 0`; RSS đỉnh PID 1 (`VmHWM`) **173 MiB**; chênh giữa đỉnh cgroup và RSS đỉnh của PID 1 ≈ 131 MiB (gồm `soffice` lúc chuyển đổi và bộ đệm tệp) |

Kết luận so với điều kiện đã định: **không vi phạm** hạn chót lượt WV-02 khi `soffice` chạy cạnh `api` ở 0,1 CPU (dư địa ≈ 7,9 s: phụ trội của một lượt khi `soffice` chạy ≈ 8 s ngoài thời gian provider, nên mỗi lời gọi P1/P2 thật chỉ được chậm tới ≈ 6 s trước khi lượt thua hạn chót; số P1/P2 thật ở mục Điều kiện trước AC-1.1 của `11-ops.md`), và `SIGTERM` giữa chuyển đổi thoát trong ≈ 2 s, trong hạn ≈ 5 s.

## Phát hiện (đều đã xử lý trong B9a2 — trừ khi ghi khác)

1. **Zombie khi Python là PID 1** (`pid1_probe.py`, image `test`, đo trước khi có bộ dọn): sau **mỗi** lần chuyển đổi bình thường nằm lại **5 zombie** (`gpgconf` ×3, `gpg`, `gpgsm` — LibreOffice gọi chúng khi khởi động rồi cha của chúng chết), và thêm một `soffice.bin` khi chuyển đổi bị giết giữa chừng. Python không `wait` tiến trình mồ côi nên chúng ở lại tới khi container chết — một service sống lâu làm đầy bảng tiến trình. **Xử lý:** `observability.reaper` (chỉ chạy khi `os.getpid() == 1`), dọn zombie con trực tiếp mà mã của ta không tự `wait`, luật hai lần quét, quét cuối khi thoát; `api_main`, `worker_main`, `combined_main` đều dùng. Đóng câu hỏi PID 1 từ B8 cho `soffice`.
2. **Thoát mềm quá chậm ở 0,1 CPU:** bản đầu của `combined_main` kết thúc bằng `sys.exit` — log `PROCESS_EXIT` ghi lúc +1,3 s sau `SIGTERM` nhưng container chỉ dừng lúc **+10,4 s** (quan sát bằng `docker top`: `python` còn chạy suốt khoảng đó; hoàn tất interpreter ở 10 % CPU). Quá hạn 5 s. **Xử lý:** thoát cứng `os._exit` sau khi mọi thứ đã đóng tường minh và log đã xả. Sau đó: +2,3 s.
3. **`ProviderClient` đặt `trust_env=False`:** `SSL_CERT_FILE` không có tác dụng — lần đo đầu trượt TLS và các lượt chat rơi vào đường lỗi (trả lời nhanh sai ý) mà `turn.reply` vẫn tới. Công cụ nay kiểm máy chủ giả đã nhận đủ lời gọi (`llm_server_calls`) — số đo B và C chỉ lấy từ lần chạy có đủ 10 lời gọi.
4. **Chuyển đổi xong trước khi đo `SIGTERM`:** các lượt chat của C chiếm vài chục giây nên chuyển đổi của job đầu có thể đã xong; công cụ gửi thêm một job và chờ `soffice` xuất hiện rồi mới gửi `SIGTERM` (`D_request`).
5. **Chưa đo / còn mở:** `/tmp` của Render Free là đĩa hay RAM (A-095, chỉ đo được trên Render thật); `worker_main` tách riêng có cùng hook huỷ và bộ dọn nhưng không có test tiến trình cho ca `SIGTERM` giữa chuyển đổi (drain của nó là `BO19_SHUTDOWN_DELAY_SECONDS`, không phải WV-32).

## Chạy lại

```
docker build -t bo19-runtime . && docker build --target test -t bo19-test .
docker start pg bo19-s3
python tools/combined-probe/run_probe.py --s3-env <file-env-S3-test-ngoài-repo>     # ≈ 6–8 phút; --keep để giữ container và DB
```
Kết quả: `tools/combined-probe/out/result.json` (thư mục `out/` nằm trong `.gitignore`).
