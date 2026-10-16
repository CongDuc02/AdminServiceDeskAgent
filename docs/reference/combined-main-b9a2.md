# `combined_main` trong cgroup của Render free — số đo B9a2 (O1-6, A-095)

**Ngày đo:** 2026-10-16 · **Công cụ:** `tools/combined-probe/` (`run_probe.py`, `combined_probe.py`, `pid1_probe.py`) · **Kết quả thô của hai lần đo hợp lệ:** `docs/reference/combined-main-b9a2-result-1.json`, `combined-main-b9a2-result-2.json` (chỉ số, mã và giờ — không nội dung). Lần 2 chạy trên mã cuối cùng của lát; lần 1 trên mã trước hai sửa nhỏ về tín hiệu tới sớm (mục Phát hiện).

## Điều kiện — và chúng KHÔNG giống Render ở đâu

- **Image runtime thật** của `Dockerfile` (stage `runtime`), `combined_main` là **PID 1** của container (`python -m bo19.entrypoints.combined_main`), `--cpus=0.1 --memory=512m --memory-swap=512m` (A-095: 512 MB RAM, 0,1 CPU). PostgreSQL 18 (`pg`), SeaweedFS 4.47 (`bo19-s3`) cùng network Docker.
- **Provider LLM là một máy chủ HTTPS GIẢ** (không gọi Groq lần nào), trễ cố định **2 s** mỗi lời gọi (PO 2026-10-16), trả P1 và P2 hợp schema. `combined_main` chạy đúng đường thật tới provider (httpx → TLS → HTTP); `ProviderClient` đặt `trust_env=False` nên chứng chỉ tự ký được thêm vào đúng bộ CA của `certifi` trong container bằng một bind mount (công cụ làm việc đó). Mỗi lượt chat là hai lời gọi (P1 rồi P2) = **4 s trễ giả** trong con số "lượt chat" dưới đây; ở cả hai lần đo máy chủ giả nhận đủ 5 lượt × 2 = 10 lời gọi.
- **Mẫu `.docx` giả không có biến nội dung tự do** — job `render_document` đi hết đường thật (graph, tool, `soffice`, object storage) nhưng không gọi LLM.
- **Docker Desktop (WSL2), cgroup v2** — không phải máy của Render. `--cpus=0.1` là hạn mức băm (quota) của cgroup, đúng cơ chế nhưng không chứng minh Render cho đúng 0,1 lõi theo cùng nhịp. Số của Render thật vẫn là việc của cổng 2.x đầu tiên có Render.
- **n nhỏ:** hai lần đo, mỗi lần hai lượt nền, ba lượt khi chuyển đổi và một `SIGTERM`. Biến thiên giữa hai lần **lớn** (một lượt chat khi chuyển đổi: 11,1 s và 18,0 s). Đây là số đo, không phải thống kê.
- **Không đo tải file** (cần bản `FINAL`, B9b): phép tính bộ nhớ của B8c (≈ 2 MiB cho bốn lượt tải) giữ nguyên.

## Kết quả

| Việc đo | Lần 1 | Lần 2 (mã cuối) |
|---|---|---|
| **A. Lên `/healthz` từ lúc `docker run`** | 41,8 s | 44,3 s |
| **B. Lượt chat không có chuyển đổi (nền)** — gồm 4 s trễ giả | 6,2 s · 5,5 s | 7,4 s · 6,0 s |
| **C. Lượt chat trong lúc `soffice` chuyển đổi** (ba lượt, `soffice` hiện ra 9,2 s / 6,4 s sau khi gửi job) | 12,1 s · 11,2 s · 7,7 s (lượt 3 sau khi chuyển đổi đã xong) | 11,1 s · **18,0 s** · 13,7 s (cả ba khi `soffice` đang chạy) |
| **Đăng nhập** (argon2id ở 0,1 CPU) | 0,4–1,4 s | 0,6–2,0 s |
| **D. `SIGTERM` lúc `soffice` đang chuyển đổi** (`docker kill -s TERM`, như Render) — log: `JOB_RELEASED_ON_DRAIN` / `PROCESS_EXIT`, mã 0 | +1,1 s / **+1,6 s**; container dừng (quan sát bằng `docker top`) **+2,3 s**; nhân chứng `pg_stat_activity`: kết nối biến mất **+1,70 s** | +1,9 s / **+2,5 s**; container dừng **+3,3 s**; nhân chứng: kết nối biến mất **+2,64 s** |
| **D'. Job sau `SIGTERM`** | `QUEUED`, `attempts = 0`, `document` `DRAFT` | như lần 1 |
| **D''. Bảng tiến trình lúc thoát** (`PROCESS_TABLE_AT_EXIT`) | `children 0`, `zombies 0`, `reaped 5`; `docker top`: `soffice` biến mất +1,47 s, rồi trống | `children 0`, `zombies 0`, `reaped 1`; `docker top`: `oosplash` và `soffice.bin` biến mất trước +3,2 s, rồi trống |
| **E. Bộ nhớ** (sau B, C; trước D) | đỉnh cgroup **304 MiB** / 512 MiB, `oom_kill 0`, `VmHWM` PID 1 173 MiB | đỉnh cgroup **308 MiB**, `oom_kill 0`, `VmHWM` PID 1 169 MiB |

**So với điều kiện đã định:**
- **Hạn chót lượt WV-02 = 20 s: không vi phạm, nhưng lần 2 chỉ còn 2,0 s dư ở lượt tệ nhất** (18,0 s). Phụ trội của một lượt khi `soffice` chạy cạnh `api` ở 0,1 CPU: **+4 đến +12 s** so với lượt nền (5,5–7,4 s) — phần lớn là tranh CPU với `soffice`. Mỗi giây P1/P2 thật chậm hơn mức 2 s giả định cộng 2 s vào lượt (hai lời gọi nối tiếp), nên chỉ cần mỗi lời gọi chậm hơn ≈ 1 s là lượt tệ nhất của lần 2 chạm 20 s. Số P1/P2 thật ở mục Điều kiện trước AC-1.1 của `11-ops.md`.
- **`SIGTERM` giữa chuyển đổi: không vượt ≈ 5 s** (A-031, S4): container dừng +2,3 s và +3,3 s. Chậm hơn ở lần 2 vì giết `soffice` và `release` cũng tranh CPU với chính nó (0,1 CPU).
- **Không `soffice` mồ côi, không zombie** ở cả hai lần.

## Phát hiện (đều đã xử lý trong B9a2, trừ khi ghi khác)

1. **Zombie khi Python là PID 1** (`pid1_probe.py`, image `test`, đo trước khi có bộ dọn): sau **mỗi** lần chuyển đổi bình thường nằm lại **5 zombie** (`gpgconf` ×3, `gpg`, `gpgsm` — LibreOffice gọi chúng khi khởi động rồi cha của chúng chết), và thêm một `soffice.bin` khi chuyển đổi bị giết giữa chừng. Python không `wait` tiến trình mồ côi nên chúng ở lại tới khi container chết — một service sống lâu làm đầy bảng tiến trình. **Xử lý:** `observability.reaper` (chỉ chạy khi `os.getpid() == 1`), dọn zombie con trực tiếp mà mã của ta không tự `wait`, luật hai lần quét, quét cuối khi thoát; `api_main`, `worker_main`, `combined_main` đều dùng. Đóng câu hỏi PID 1 từ B8 cho `soffice`.
2. **Thoát mềm quá chậm ở 0,1 CPU:** bản đầu của `combined_main` kết thúc bằng `sys.exit` — log `PROCESS_EXIT` ghi lúc +1,3 s sau `SIGTERM` nhưng container chỉ dừng lúc **+10,4 s** (quan sát bằng `docker top`: `python` còn chạy suốt khoảng đó; hoàn tất interpreter ở 10 % CPU). Quá hạn 5 s. **Xử lý:** thoát cứng `os._exit` sau khi mọi thứ đã đóng tường minh và log đã xả; đột biến "quay lại `sys.exit`" đỏ cả ở test tiến trình trong CI.
3. **`SIGTERM` tới trước khi uvicorn cài bộ xử lý của nó bị mất:** test tiến trình (gửi `SIGTERM` ngay sau `WORKER_LOOP_START`) treo 30 s dưới tải rồi tái hiện được ổn định — bộ xử lý gốc chỉ ghi log, uvicorn cài bộ xử lý sau đó và chạy mãi. **Xử lý:** bộ xử lý gốc của `combined_main` dừng vòng poll, và một luồng cầu nối đặt `should_exit` của uvicorn khi thấy tín hiệu đã ghi. **`api_main` có cùng khoảng hở** — chưa sửa (ngoài kế hoạch B9a2); báo PO.
4. **`ProviderClient` đặt `trust_env=False`:** `SSL_CERT_FILE` không có tác dụng — lần đo đầu trượt TLS và các lượt chat rơi vào đường lỗi (trả lời nhanh sai ý) mà `turn.reply` vẫn tới. Công cụ nay ghi `llm_server_calls` — số đo chỉ lấy từ các lần chạy máy chủ giả nhận đủ lời gọi.
5. **Chuyển đổi xong trước khi đo `SIGTERM`:** các lượt chat của C chiếm vài chục giây nên chuyển đổi của job đầu có thể đã xong; công cụ gửi thêm một job và chờ `soffice` xuất hiện rồi mới gửi `SIGTERM` (`D_request`). Lần 2 không cần (chuyển đổi còn chạy).
6. **Chưa đo / còn mở:** `/tmp` của Render Free là đĩa hay RAM (A-095, chỉ đo được trên Render thật); mức tăng RSS theo thời gian dài; `worker_main` tách riêng có cùng hook huỷ và bộ dọn nhưng không có test tiến trình cho ca `SIGTERM` giữa chuyển đổi (drain của nó là `BO19_SHUTDOWN_DELAY_SECONDS`, không phải WV-32).

## Chạy lại

```
docker build -t bo19-runtime . && docker build --target test -t bo19-test .
docker start pg bo19-s3
python tools/combined-probe/run_probe.py --s3-env <file-env-S3-test-ngoài-repo>     # ≈ 6–8 phút; --keep để giữ container và DB
```
Kết quả: `tools/combined-probe/out/result.json` (thư mục `out/` nằm trong `.gitignore`).
