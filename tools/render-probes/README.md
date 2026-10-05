# tools/render-probes — S3 của Spike 1

Đo từ **ngoài** Render: proxy có gom đệm response `text/event-stream` không (A-050), một request sống được bao lâu (A-025). Kết quả là của **Web Service free** — không suy ra cho gói trả phí.

**S3 xong, 2026-10-04–05.** Kết quả: `docs/reference/render-s3-nhat-ky-do.md`; ghi vào A-025, A-050, A-086 của `docs/design/ASSUMPTIONS.md`.

**Đã gỡ ở bước 7:** khối `SPIKE S3` của `backend/src/bo19/entrypoints/api_main.py`, `backend/tests/test_spike_probes.py`, workflow `.github/workflows/spike-s3-probe.yml` và `run.json`. Endpoint `/api/_spike/*` **không còn** — `probe.py` không chạy được nếu không khôi phục khối đó từ lịch sử git (commit `91a0fcf`) và đặt lại `BO19_SPIKE_PROBES`, `BO19_SPIKE_TOKEN`. Giữ lại `probe.py`, `test_probe.py` (chỉ thư viện chuẩn, chạy độc lập với server) và README này để người sau đọc phương pháp và ngưỡng, hoặc đo lại ở Sprint 4 (A-086). Các đoạn dưới đây mô tả cách chạy **trong lúc S3 diễn ra**.

## Endpoint (dưới `/api/_spike`)

Chỉ có khi `BO19_SPIKE_PROBES=1` và `BO19_SPIKE_TOKEN` khác rỗng. Header `X-BO19-Spike-Token` sai hoặc thiếu → 404 giống hệt đường dẫn lạ. Thứ tự kiểm: cờ → token → trần tham số (400) → kết nối thử thứ hai (429).

| Đường dẫn | Việc | Trần |
|---|---|---|
| `/sse?interval=&max=&kind=&accel=` | Một event `open` ngay khi kết nối; rồi mỗi `interval` giây một event `tick` (`kind=event`, mặc định) hoặc một dòng comment (`kind=comment`); `interval=0` giữ im lặng. Mỗi event mang số thứ tự và giờ máy chủ. Hết `max` giây thì gửi event `end` rồi đóng. `accel=no` thêm header `X-Accel-Buffering: no` | `max` ≤ 3600 s; `interval` = 0 hoặc ≥ 0.1 |
| `/sleep?s=` | Không trả byte nào tới khi đủ `s` giây (`asyncio.sleep`, tỉnh dậy mỗi 1 s để thấy client ngắt) | `s` ≤ 1800 s |
| `/commit` | `RENDER_GIT_COMMIT`, `RENDER_GIT_BRANCH`, `boot_epoch` của tiến trình. Không giữ chỗ thử | — |

Tối đa **một** kết nối thử (`/sse`, `/sleep`) đồng thời. Client ngắt thì chỗ trả trong tối đa 1 s.

## Chạy

```text
BO19_SPIKE_BASE_URL   gốc URL của Web Service — không in, không ghi ra file kết quả
BO19_SPIKE_TOKEN      giá trị của header — không in, không ghi ra file kết quả

python tools/render-probes/probe.py --spec run.json
python tools/render-probes/probe.py --case sse-events --interval 5 --max 600 --enc browser --expect-commit <sha>
```

Credential truyền bằng biến môi trường đọc từ file — không đặt giá trị trên dòng lệnh. Mô tả đầy đủ các case, `enc` và định dạng spec: đầu `probe.py`. Kết quả vào `tools/render-probes/out/<label>/` — thư mục này gitignore; số đo vào `docs/reference/` do người triển khai chép tay, nguyên văn.

Trước khi đo, `probe.py` hỏi `/commit`; sai commit so với `expect_commit` thì dừng (mã 3), không đo. Sau mỗi lượt đo nó hỏi `/commit` lần nữa: `boot_epoch` đổi nghĩa là tiến trình đã khởi động lại giữa chừng — đối chiếu với log Render trước khi kết luận một lần bị cắt.

## Nhiễu nền local — số đo của đối chứng, 2026-10-04

Container Linux dựng từ `Dockerfile` S2, client `probe.py` trên Windows, qua loopback. Sáu lượt: bốn ca, hai biến thể `Accept-Encoding`.

- **18 cặp event liên tiếp.** Lệch lớn nhất giữa khoảng nhận và khoảng gửi, `|recv_gap − send_gap|`: **4.237 ms** — một cặp ở lượt 2. Các lượt khác: 0.493 ms, 0.838 ms, 1.041 ms.
- Event đầu (`open`) tới sau **3.627 ms đến 8.486 ms** kể từ lúc gửi request.
- Không có `Content-Encoding` — server không nén.

Mẫu nhỏ và là loopback: đây là nền của phần mềm hai đầu, **không** phải nền của mạng. Nó chỉ cho biết ngưỡng bên dưới cao hơn nền phần mềm hơn 100 lần, nên một chênh lệch vượt ngưỡng không do code của ta.

## Ngưỡng kết luận gom đệm — đặt trước khi đo Render, 2026-10-04

Áp cho ca `sse-events` và `sse-comment`, nhịp `I = 5 s`. Máy chủ gửi `open` ngay khi kết nối và gửi mỗi nhịp đúng giờ, nên mọi độ trễ hay dồn đều do đường đi.

| Kết luận | Điều kiện — cả hai biến thể `enc` |
|---|---|
| **Không thấy gom đệm** | `open` tới sau ≤ 2 s **và** mọi cặp `|recv_gap − send_gap|` ≤ 0.5 s (= 0.1 · I; 118 lần nền local) |
| **Có gom đệm** | `open` tới sau ≥ 5 s (= I) dù máy chủ gửi ngay, **hoặc** ≥ **2** cặp có `|recv_gap − send_gap|` ≥ 2.5 s (= 0.5 · I) trong **cùng một lượt**, **hoặc** một cặp như vậy xuất hiện lại ở lượt chạy lại |
| **Không kết luận** | Mọi trường hợp còn lại — gồm **một cặp lệch ≥ 2.5 s đơn lẻ** trong một lượt: ghi số, **chạy lại** lượt đó; không gán nhãn |

- Một cặp lệch ≥ 2.5 s đơn lẻ có thể là một đợt trễ mạng, không phải gom đệm — vì vậy cần hai cặp hoặc một lần lặp lại. Sửa ngưỡng này (PO, 2026-10-04) trước khi có số đo Render nào.
- Một kết luận cần hai lượt (mỗi biến thể `enc` một lượt) cùng chiều. Lệch nhau thì lặp lại; vẫn lệch thì ghi cả hai.
- `body_decodable = false` (ví dụ `br`): áp cùng ngưỡng lên thời điểm của từng chunk (`chunks[].t`) thay cho event; ghi rõ.
- Nếu gom đệm: đo thêm biến thể `accel=no` (`X-Accel-Buffering: no`), cùng ngưỡng.
- Số 2 s, 0.5 s, 2.5 s là **chọn**, không suy từ nền local — nền chỉ bảo đảm chúng nằm trên nhiễu của phần mềm.

## Quy trình đo A-025 — PO duyệt 2026-10-04

- **Thang `sleep`:** 30, 60, 120, 300, 600, 1800 s. Bị cắt ở nấc nào thì chia đôi khoảng giữa nấc đó và nấc ngay dưới (hoặc 0 s), dừng khi khoảng `hi − lo` ≤ `max(15 s, 10% · lo)`.
- **SSE im lặng** (`sse-silent`): tới khi bị cắt, trần 60 phút. Không cắt thì ghi "≥ 60 phút".
- **Tới trần mà không bị cắt:** ghi "≥ trần", không ghi "không giới hạn".
- **Điểm cắt và nấc ngay dưới** mỗi cái chạy lại ít nhất 2 lần.
- **Mỗi lần cắt:** đối chiếu log Render xem có restart, deploy hay spin-down (gói free ngủ sau 15 phút không có traffic vào) trong lúc đo. `boot_epoch` đổi giữa hai lần `/commit` là một bằng chứng; log Render là bằng chứng còn lại.
- **Chỗ chạy — PO, 2026-10-04:** ca dài (thang `sleep`, `sse-silent`, `sse-comment` ≥ 15 phút) **chỉ chạy từ runner**. Máy nhà chỉ chạy ca ngắn (SSE nhịp 5 s, 10 phút), làm điểm nhìn thứ hai cho A-050. Lý do: router/NAT nhà có thể tự cắt kết nối nhàn rỗi và làm sai ca (b); và một phiên bị ngắt giữa chừng làm mất lượt đo.
- **Ca dài (≥ 15 phút), mỗi ca chạy hai lần** — có và không có `curl /healthz` mỗi 5 phút từ ngoài (`keepwarm_s` trong spec; workflow tự chạy vòng lặp đó). Hai lần là hai push `run.json` riêng.
- **`boot_epoch` đổi trong lượt ⇒ lượt đó là `restart`, không tính là điểm cắt.** Probe so `boot_epoch` trước lượt với sau lượt (một lần `/commit` sau lượt, có thể chính nó đánh thức service đang ngủ). Không hỏi lại được `/commit` thì `cut_unverified` — không khẳng định gì.
- **Một kết nối bị cắt có thể do nhiều nguyên nhân** — mạng nhà, NAT, restart, spin-down, giới hạn của Render. Một lần cắt chỉ là điểm dữ liệu; kết luận về giới hạn cần điểm cắt lặp lại, cùng giá trị, nhiều nơi gọi (máy nhà và runner), không có restart.
- **Ca (b) im lặng sau header:** máy chủ không biết lúc nó bị cắt — chỉ khi proxy báo client ngắt thì log mới có `reason=cancelled` / `client_gone`, và chính việc có hay không là một quan sát. Kết luận dựa trên phía client (`ended`, `elapsed_s`) và log Render, không dựa vào `SPIKE_END` của ta.
- **Gặp 429:** `probe.py` chờ rồi thử lại, ghi `busy_retries`, không tính là điểm dữ liệu.
- **Giới hạn đã chấp nhận:** `probe.py` nói HTTP/1.1; trình duyệt qua Render có thể dùng HTTP/2. Mọi kết quả ghi rõ điều này.

## Ghi tăng dần và nhãn — PO, 2026-10-04

- Mỗi lượt ghi `out/<label>/NN-<case>-<enc>.jsonl`: một dòng cho mỗi sự kiện — `meta`, `start`, `response`, `chunk`, `event` (kèm `server_epoch` và `wall` giờ nhận), `end`, `after`, `final` — flush ngay. Mọi dòng qua bước che host. File JSON cuối của một lượt hoàn tất vẫn có.
- **Lượt chết giữa chừng giữ dữ liệu tới điểm chết.** Thiếu dòng `end` là lượt **gián đoạn**. `probe.py --summarize <file|thư mục>` đọc lại, bỏ dòng cuối bị cắt dở.
- **Không áp ngưỡng nếu chưa đủ cặp:** lượt gián đoạn dưới **60 cặp** event (nửa số cặp của lượt 10 phút nhịp 5 s) ghi "gián đoạn — không áp ngưỡng". Từ 60 cặp trở lên mới áp ngưỡng, và kết luận mang nhãn "dữ liệu một phần". Mốc 60 là **chọn**.
- Nhãn `classification` của lượt hoàn tất: `completed` · `cut` (kết nối chấm dứt không có event `end`, `boot_epoch` không đổi) · `restart` · `cut_unverified` · `busy_gave_up`. Lượt gián đoạn không có `classification` của probe — nó đã chết trước khi hỏi `/commit`.
- Trên runner, đĩa mất khi job kết thúc hay bị huỷ: `--emit` in từng dòng JSONL ra log dưới tiền tố `JOURNAL`, nên dữ liệu tới điểm huỷ vẫn nằm trong log.
- Giết thử bằng test: `test_probe.py`, lớp `BiGietGiuaChung`.

## Runner GitHub Actions

`.github/workflows/spike-s3-probe.yml` — trigger `push` lên `spike/s3-do` **và** `paths: tools/render-probes/run.json`. Commit thường, kể cả lần push đầu của nhánh, không chạy. Một lượt chạy = một push đổi `run.json`.

`run.json` mang `label`, `expect_commit` (commit Render đang chạy — **không** phải commit của lần push, vì Render chỉ deploy commit người ta bấm), `keepwarm_s` (tuỳ chọn) và `runs`. Tổng thời lượng ước tính ≤ 330 phút, dưới trần 360 phút của job. Nhiều vòng thì chia nhiều push; `concurrency` chỉ cho một lượt chạy, một lượt chờ — chờ lượt trước xong rồi mới push tiếp.

Secret của repo: `BO19_SPIKE_BASE_URL`, `BO19_SPIKE_TOKEN` — PO tạo, xoá ở bước 7. Kết quả in thành các dòng `JOURNAL` (từng sự kiện) và `RESULT_JSON` (kết quả cuối của lượt) trong log của job.

## Thu hẹp S3 — PO, 2026-10-04

**Mục "Quy trình đo A-025" ở trên được thu hẹp**; phần còn lại của nó (thang dài, chia đôi, ca ≥ 15 phút, `keepwarm`, chạy lại ≥ 2 lần) **không chạy — không quyết định nào cần**. Còn chạy trên runner, rồi dừng đo:

1. `sse-events`, `interval=5`, `max=600`, `enc=none` và `enc=browser` — điểm nhìn thứ hai cho A-050. Báo theo **cả** ngưỡng gốc **và** tiêu chí phụ dưới đây.
2. `sse-silent`, `max` = 30, 60, 120, 300 s, `enc=none`. Dừng ở nấc bị cắt đầu tiên; không chia đôi (`"ladder": "silent"` trong spec).
3. `sleep`, `s` = 30, 60, 120, `enc=none`. Dừng ở nấc bị cắt đầu tiên; không chia đôi (`"ladder": "sleep"`).

Mỗi nấc chạy **một** lần. Một nấc có `boot_epoch` đổi trong lượt là `restart`, không phải điểm cắt và không dừng thang. Tổng thời lượng ước tính: 1920 s đo + 9 × 60 s dự phòng = 2460 s ≈ 41 phút, trong một job.

## Tiêu chí phụ cho A-050 — đặt trước khi đo trên runner, 2026-10-04

Ba lượt local (`short-2` `none`, `short-2` `browser`, `short-3` `none`) cho lệch lớn nhất 0.540 s, 0.352 s, 0.608 s — hai trong ba vượt mốc 0.5 s của ngưỡng gốc, trong khi `bunched_pairs` = 0 và không cặp nào ≥ 2.5 s. Mốc 0.5 s nằm trong vùng nhiễu của đường mạng nhà. **Tiêu chí phụ được đặt sau khi đã thấy dữ liệu local** — ghi rõ, và không thay ngưỡng gốc: mọi lượt được báo theo cả hai, cạnh nhau.

| Kết luận (phụ) | Điều kiện |
|---|---|
| **Không thấy gom đệm** | `open` tới sau ≤ 2 s **và** không cặp nào dồn (`bunched_pairs` = 0: nhận cách nhau < nửa khoảng gửi) **và** mọi cặp `|recv_gap − send_gap|` ≤ **1.0 s** (= 0.2 · I) |
| **Có gom đệm** | Như ngưỡng gốc: `open` tới sau ≥ I, **hoặc** ≥ 2 cặp lệch ≥ 2.5 s trong một lượt, **hoặc** một cặp như vậy lặp lại |
| **Không kết luận** | Còn lại, gồm một cặp lệch ≥ 2.5 s đơn lẻ (chạy lại) |

Chỉ khác ngưỡng gốc ở mốc "không thấy": 0.1 · I → 0.2 · I, cộng điều kiện `bunched_pairs` = 0. Mốc 1.0 s là **chọn**: 1.6 lần lệch lớn nhất đã thấy ở local; không suy từ lý thuyết. Áp ngược cho ba lượt local, cả ba là "không thấy gom đệm" theo tiêu chí phụ, hai trong ba là "không kết luận" theo ngưỡng gốc. Trong `probe.py`: `verdict` (gốc) và `verdict_phu`.

## S4 xong — `s4_witness_poll.py`, đo lại trước production (A-087)

**S4 xong, 2026-10-05.** Kết quả: `docs/reference/render-s4-nhat-ky-do.md`; ghi vào A-031, A-086, A-087. Trên Web Service free: `SIGKILL` ≈ 5 s sau `SIGTERM` ((4.9, 5.2] s, có nhân chứng), cả deploy lẫn ngủ. Khối `SPIKE S4` của `api_main.py` và test của nó **đã gỡ**; **giữ** `s4_witness_poll.py` và `test_s4_witness.py` để đo lại **trước production, trên gói trả phí** (điều kiện A-087, mục Sau UAT của `docs/design/12-roadmap.md`).

**Điều kiện để đo lại.** Bộ poll chỉ đọc một kết nối PostgreSQL mà app phải mở sẵn. Khối cần khôi phục từ lịch sử git: bản `api_main.py` ở commit `83591ee` (kết nối nhân chứng mở lúc khởi động, `application_name` = `s4 boot=<boot_utc> n=<k>`, vòng giữ `SHUTDOWN_HOLD`, ghi mọi tín hiệu, log uvicorn có giờ UTC) và `backend/tests/test_spike_s4.py` cùng commit. Chỉ bật khi đặt `BO19_S4_HOLD_S` (ví dụ 120). Nếu start command đã là `combined_main` (O1-6), khối đó phải được đặt vào entrypoint thật Render chạy.

**Cách đo**, một lần deploy sạch rồi một lần ngủ:

1. Deploy bản có khối S4 lên gói trả phí, đặt `BO19_S4_HOLD_S=120`. Kiểm log có `WITNESS_OPEN` và `S4_ARMED … witness=True`.
2. Từ máy người triển khai chạy bộ poll — credential `bo19_app` **chỉ** qua biến môi trường `BO19_S4_POLL_DSN` đọc từ file, không trên dòng lệnh, không in. Máy chủ Windows của dự án không có `psycopg`; chạy trong image của dự án (`docker run --env-file … -v tools/render-probes:/tools:ro <image> python /tools/s4_witness_poll.py --duration 1800 > poll.jsonl`).
3. **Manual Deploy một lần**, không có request nào khác. Đọc log của instance cũ: `SIGNAL_RECEIVED` (mọi dòng), `SIGTERM_RECEIVED`, `SHUTDOWN_HOLD`.
4. Gói trả phí có thể không ngủ; nếu có, để yên ≥ 15 phút để lấy đường ngủ. Ghi giờ request cuối trong access log.
5. `python s4_witness_poll.py --analyze poll.jsonl --sigterm <giờ SIGTERM_RECEIVED trong log>`.

**Báo riêng hai số:** (a) `n` cuối đọc được, (b) lúc kết nối biến mất. Nhãn theo **ba kết quả khai báo trước** ở mục Khai báo trước kết quả của nhân chứng của nhật ký S4 — kill ≈ T s (n dừng ở T, biến mất ngay), log bị cắt (n tiếp tục tăng), treo (n dừng, kết nối còn ≥ 10 s) — hoặc "không gán nhãn". Đặt các ngưỡng **trước** khi deploy, không sửa sau khi có số.

**Rồi `maxShutdownDelaySeconds`** (mặc định 30 s, tối đa 300 s; đặt qua API hoặc `render.yaml` theo `docs/reference/render-deploys-docker.md`): đặt một giá trị khác mặc định rồi đo lại bằng cùng bộ — PO quyết lúc đó. Trên gói free **không thử** (PO, 2026-10-05).

**Hai bài học của S4:** log của Render không phân biệt được kill với cắt log (cùng n=5 sáu lần) — chỉ nhân chứng độc lập với log phân biệt được; và một deploy hay một lần đo đúng lúc instance đang tắt vì ngủ có thể hỏng (`Port scan timeout`) — wake bằng một request, rồi bấm deploy ngay.
