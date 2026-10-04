# tools/render-probes — S3 của Spike 1

Đo từ **ngoài** Render: proxy có gom đệm response `text/event-stream` không (A-050), một request sống được bao lâu (A-025). Kết quả là của **Web Service free** — không suy ra cho gói trả phí.

Tạm thời: cùng khối `SPIKE S3` ở `backend/src/bo19/entrypoints/api_main.py` và `backend/tests/test_spike_probes.py`, gỡ hẳn ở bước 7 của S3.

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
| **Có gom đệm** | `open` tới sau ≥ 5 s (= I) dù máy chủ gửi ngay, **hoặc** ≥ 1 cặp có `|recv_gap − send_gap|` ≥ 2.5 s (= 0.5 · I; một event bị giữ lại thường kéo theo một cặp dồn, tức `bunched_pairs` ≥ 1) |
| **Không kết luận** | Mọi trường hợp còn lại — ghi số, không gán nhãn |

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
- **Ca dài (≥ 15 phút):** chạy hai lần — có và không có `curl /healthz` mỗi 5 phút từ ngoài (`keepwarm_s` trong spec; workflow tự chạy vòng lặp đó).
- **Một kết nối bị cắt có thể do nhiều nguyên nhân** — mạng nhà, NAT, restart, spin-down, giới hạn của Render. Một lần cắt chỉ là điểm dữ liệu; kết luận về giới hạn cần điểm cắt lặp lại, cùng giá trị, nhiều nơi gọi (máy nhà và runner), không có restart.
- **Ca (b) im lặng sau header:** máy chủ không biết lúc nó bị cắt — chỉ khi proxy báo client ngắt thì log mới có `reason=cancelled` / `client_gone`, và chính việc có hay không là một quan sát. Kết luận dựa trên phía client (`ended`, `elapsed_s`) và log Render, không dựa vào `SPIKE_END` của ta.
- **Gặp 429:** `probe.py` chờ rồi thử lại, ghi `busy_retries`, không tính là điểm dữ liệu.
- **Giới hạn đã chấp nhận:** `probe.py` nói HTTP/1.1; trình duyệt qua Render có thể dùng HTTP/2. Mọi kết quả ghi rõ điều này.

## Runner GitHub Actions

`.github/workflows/spike-s3-probe.yml` — trigger `push` lên `spike/s3-do` **và** `paths: tools/render-probes/run.json`. Commit thường, kể cả lần push đầu của nhánh, không chạy. Một lượt chạy = một push đổi `run.json`.

`run.json` mang `label`, `expect_commit` (commit Render đang chạy — **không** phải commit của lần push, vì Render chỉ deploy commit người ta bấm), `keepwarm_s` (tuỳ chọn) và `runs`. Tổng thời lượng ước tính ≤ 330 phút, dưới trần 360 phút của job. Nhiều vòng thì chia nhiều push; `concurrency` chỉ cho một lượt chạy, một lượt chờ — chờ lượt trước xong rồi mới push tiếp.

Secret của repo: `BO19_SPIKE_BASE_URL`, `BO19_SPIKE_TOKEN` — PO tạo, xoá ở bước 7. Kết quả in thành các dòng `RESULT_JSON` trong log của job.
