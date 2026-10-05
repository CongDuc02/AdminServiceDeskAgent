# psycopg 3.3.5 — thông báo lỗi khi nối PostgreSQL thất bại (quan sát, không phải tài liệu)

- **Loại tài liệu này:** **quan sát chạy thật**, không phải trích dẫn tài liệu sản phẩm. Lý do: mã khởi động cần phân biệt "sai mật khẩu" với "không tới được host" (O1-4 của `12-roadmap.md`; S2 ghi `sqlstate=None` ở cả hai — `render-web-service-s2.md`), và thông báo của libpq không có trong tài liệu nào đã lấy. Chuỗi dưới đây là điều **đã thấy** ở bản này; một bản libpq khác có thể đổi chữ — phải chạy lại khi lock đổi `psycopg` (A-081).
- **Ngày:** 2026-10-05. **Bản:** `psycopg` 3.3.5, `psycopg-binary` (libpq `180006`, đọc từ `psycopg.pq.version()`), PostgreSQL `pgvector/pgvector:0.8.1-pg18` (ADR-033) trong một mạng Docker riêng, `POSTGRES_PASSWORD` đặt (xác thực mật khẩu qua mạng). Địa chỉ IP của container thay bằng `<ip>`; mật khẩu thử thay bằng `<pw>`.
- **Dùng cho:** B2 — `bo19.startup.runner`, `classify_connect_error` (O1-4). Log **không** ghi nguyên văn thông báo (có thể mang host); chỉ ghi lớp phân loại.

## Kết quả

| Ca | Lớp ngoại lệ | `sqlstate` | Thông báo (`str(e)`) |
|---|---|---|---|
| sai_mat_khau | `OperationalError` | None | `connection failed: connection to server at "<ip>", port 5432 failed: FATAL:  password authentication failed for user "postgres"` |
| role_khong_ton_tai | `OperationalError` | None | `connection failed: connection to server at "<ip>", port 5432 failed: FATAL:  password authentication failed for user "khong_co_role"` |
| database_khong_co | `OperationalError` | None | `connection failed: connection to server at "<ip>", port 5432 failed: FATAL:  database "khong_co_db" does not exist` |
| cong_dong | `OperationalError` | None | `connection failed: connection to server at "<ip>", port 5999 failed: Connection refused  Is the server running on that host and accepting TCP/IP connections?` |
| host_khong_phan_giai | `OperationalError` | None | `failed to resolve host 'host-khong-ton-tai.invalid': [Errno -2] Name or service not known` |
| timeout | `ConnectionTimeout` | None | `connection timeout expired` |
| dung | `—` | None | `(kết nối được)` |

Trừ `ConnectionTimeout` (lớp riêng), mọi lỗi là `OperationalError` với `sqlstate=None` — **không dùng `sqlstate`** để phân loại.

## Quy tắc phân loại rút ra — chỉ từ bảng trên

| Phân loại | Điều kiện | Ca đã thấy |
|---|---|---|
| `AUTH` | thông báo chứa `authentication failed` | `sai_mat_khau`, `role_khong_ton_tai` |
| `NETWORK` | lớp `ConnectionTimeout`, hoặc thông báo chứa `failed to resolve host` hay `Connection refused` | `cong_dong`, `host_khong_phan_giai`, `timeout` |
| `OTHER` | mọi trường hợp khác — gồm `database_khong_co` (máy chủ trả lời, không phải lỗi xác thực) và mọi thông báo chưa thấy | `database_khong_co` |

Không có lớp `OTHER` thì một thông báo chưa từng thấy bị đẩy vào `AUTH` hay `NETWORK` và dẫn người vận hành đi sai hướng. `pg_hba.conf` từ chối, SSL bắt buộc, quá số kết nối… **chưa quan sát** — rơi vào `OTHER` cho tới khi có bằng chứng.

## Script đã chạy (mật khẩu thử giả, container dùng một lần)

```python
import psycopg, json
PW="ThuNghiem123"
cases = {
 "sai_mat_khau":      "postgresql://postgres:SAI_MAT_KHAU@pgce:5432/postgres",
 "role_khong_ton_tai":"postgresql://khong_co_role:x@pgce:5432/postgres",
 "database_khong_co": f"postgresql://postgres:{PW}@pgce:5432/khong_co_db",
 "cong_dong":         f"postgresql://postgres:{PW}@pgce:5999/postgres",
 "host_khong_phan_giai": f"postgresql://postgres:{PW}@host-khong-ton-tai.invalid:5432/postgres",
 "timeout":           f"postgresql://postgres:{PW}@10.255.255.1:5432/postgres",
 "dung":              f"postgresql://postgres:{PW}@pgce:5432/postgres",
}
for name, dsn in cases.items():
    try:
        with psycopg.connect(dsn, connect_timeout=3) as c: print(json.dumps({"case":name,"result":"OK"}))
    except Exception as e:
        print(json.dumps({"case":name,"class":type(e).__name__,"sqlstate":getattr(e,"sqlstate",None),"msg":str(e).replace(PW,"<pw>")}, ensure_ascii=False))
```
