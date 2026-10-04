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
