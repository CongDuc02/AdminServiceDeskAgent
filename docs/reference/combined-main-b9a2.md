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

## Hạ ưu tiên `soffice` (`nice -n 19`, WV-33) — đo trước/sau, 2026-10-20

**Yêu cầu của PO:** hạ ưu tiên `soffice` khi khởi chạy để `api` được ưu tiên CPU trong 0,1 CPU; đo lại "lượt chat khi `soffice` chạy" (n ≥ 3), báo trước/sau; job render chậm hơn là chấp nhận được.

**Cài đặt:** `soffice` chạy qua `nice -n 19` (`convert.niced`); `nice` `exec` thẳng vào `soffice` nên PID và nhóm tiến trình không đổi; bước kiểm #6 đòi có `nice` (`STARTUP_06_NICE_MISSING`). Test chứng minh tiến trình `soffice` thật mang niceness 19 (đọc `/proc/<pid>/stat`). **Giá trị 19 và lý do:** trọng số CFS nice 0 = 1024, nice 19 = 15 → khi tranh, `api` ≈ 98,5 %; lúc `api` rảnh (phần lớn thời gian) `soffice` vẫn nhận gần đủ hạn mức nên chỉ chậm khi có tải chat; 19 là thấp nhất nên không còn nấc nào để tinh chỉnh.

**Đo:** cùng công cụ `tools/combined-probe/`, hai image dựng từ hai commit — "trước" = `4a74f61` (không `nice`), "sau" = có `nice` — chạy **xen kẽ** (trước, sau, trước, sau) để trôi theo thời gian không dồn về một phía, mỗi điều kiện hai lần, mỗi lần gom **≥ 3 lượt chat có `soffice` chạy cả trước và sau lượt** (gửi thêm job khi chuyển đổi xong mà chưa đủ). Thêm hai lần × hai điều kiện với container **ghim vào một CPU** (`docker --cpuset-cpus=0`) — lý do ở mục kế. Kết quả thô: `docs/reference/combined-main-b9a2-nice/`.

| Điều kiện (n = 6 lượt chat khi `soffice` chạy) | nhỏ nhất | trung vị | trung bình | lớn nhất | các lượt (s) |
|---|---|---|---|---|---|
| **trước** (không `nice`), không ghim | 8,8 | **11,7** | 13,4 | **21,1** | 8,8 · 10,9 · 11,2 · 12,1 · 16,3 · 21,1 |
| **sau** (`nice` 19), không ghim | 10,2 | **11,8** | 13,2 | **19,1** | 10,2 · 11,4 · 11,6 · 12,1 · 15,0 · 19,1 |
| trước, ghim 1 CPU | 8,0 | 8,6 | 10,6 | 16,8 | 8,0 · 8,2 · 8,5 · 8,6 · 13,4 · 16,8 |
| **sau, ghim 1 CPU** | 6,6 | **8,4** | 8,1 | **9,9** | 6,6 · 6,7 · 8,1 · 8,7 · 8,7 · 9,9 |

| Thông số (hai lần mỗi điều kiện) | trước | sau | trước, ghim | sau, ghim |
|---|---|---|---|---|
| Lượt chat nền, không chuyển đổi (s) | 8,1 · 5,7 · 7,8 · 5,8 | 9,1 · 5,9 · 6,4 · 5,3 | 8,4 · 5,3 · 5,8 · 5,1 | 6,3 · 5,3 · 5,7 · 5,4 |
| **Job render một mình**, gửi → `SUCCEEDED` (s) | 77,4 · 62,5 | 76,4 · 42,8 | 50,3 · 41,4 | 40,2 · 43,6 |
| Lên `/healthz` (s) | 62,6 · 61,4 | 78,8 · 44,9 | 38,8 · 43,8 | 40,7 · 41,8 |
| `SIGTERM`: container dừng (s) | 3,4 · 2,8 | 3,4 · 2,1 | 2,5 · 2,3 | 2,2 · 2,2 |
| Đỉnh cgroup (MiB), `oom_kill` | 328 · 306, 0 | 301 · 322, 0 | 318 · 349, 0 | 334 · 315, 0 |

**Kết quả — nói thẳng:**
- **`nice` một mình KHÔNG cải thiện được lượt chat**: trung vị 11,7 s → 11,8 s, trung bình 13,4 → 13,2 s; lớn nhất 21,1 → 19,1 s nằm trong nhiễu của n = 6 (biến thiên giữa hai lần chạy cùng điều kiện lớn hơn chênh lệch trước/sau; lên `/healthz` của cùng một image dao động 44,9–78,8 s). **Trong điều kiện "trước" đã có một lượt 21,1 s — vượt hạn chót WV-02 (20 s)**; "sau" có lượt 19,1 s, sát hạn.
- **Job render không chậm đi**: 77/63 s → 76/43 s (khi `api` rảnh, `soffice` vẫn nhận gần đủ hạn mức) — "job chậm hơn là chấp nhận được" chưa phải trả giá nào.
- **Vì sao `nice` không có tác dụng — đo trực tiếp (cùng cgroup `--cpus=0.1`, hai tiến trình ăn CPU liên tục, 12 s):** máy ảo thấy 12 CPU; hai tiến trình nằm trên hai CPU khác nhau (hai runqueue) nên không tranh nhau — nice 0 nhận 73 tick, nice 19 nhận 57 tick (gần bằng nhau). **Ghim cả hai vào cùng một CPU (`taskset -c 0`): nice 0 = 118 tick, nice 19 = 2 tick** — đúng mô hình trọng số. Hạn mức 0,1 CPU của cgroup là hạn mức chung; trọng số `nice` chỉ chia phần CPU giữa các tiến trình **chung một runqueue**. `sched_autogroup` không có trong nhân này nên không phải nguyên nhân.
- **Ghim container vào một CPU làm `nice` có tác dụng, và chính nó cũng giúp**: lớn nhất 21,1 → **9,9 s** (n = 6), trung vị 11,7 → 8,4 s, trung bình 13,4 → 8,1 s; lượt khi `soffice` chạy chỉ còn hơn lượt nền ≈ 3 s. Ghim mà không `nice` ("trước, ghim"): trung vị 8,6 s nhưng vẫn có lượt 16,8 s. Cần cả hai.
- **Giới hạn:** Docker Desktop (WSL2, 12 CPU ảo), không phải Render; provider giả; n = 6 mỗi điều kiện, bốn điều kiện đo trong cùng một buổi nhưng máy ngoài kiểm soát (nhiễu). `--cpuset-cpus` là thử nghiệm: trên Render không đặt được cờ này; tương đương trong mã là `os.sched_setaffinity` ghim tiến trình (con thừa kế) vào một CPU — **chưa làm, chờ PO** (ngoài kế hoạch đã duyệt).
- **Phương án mặc định đề xuất:** giữ `nice` 19 (vô hại, đã đo) **và** ghim tiến trình `combined_main` (và `worker_main`) vào một CPU khi hạn mức cgroup `cpu.max` nhỏ hơn một CPU; đo lại trên Render thật khi chuyển Start Command (cổng 2.5). Phương án khác: tạm dừng `soffice` (`SIGSTOP`/`SIGCONT`) trong lúc có lượt chat đang chạy — chắc hơn nhưng phức tạp hơn (cần `TurnSupervisor` báo cho vòng poll).
