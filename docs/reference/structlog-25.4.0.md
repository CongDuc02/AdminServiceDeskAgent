# structlog 25.4.0 — chuỗi processor và nối với `logging` chuẩn

- **Ngày lấy:** 2026-10-05, bằng `curl -sS -L` (không công cụ tóm tắt web). Phiên bản tài liệu: **25.4.0** — đúng bản `backend/requirements-linux.lock` (`structlog==25.4.0`, ADR-029, ADR-030).
- **Dùng cho:** B2, gói `bo19.observability` (`log.py`, `handler.py`): chuỗi processor có bước mask rồi xuất bản ghi qua **một** handler của `logging` gắn vào root logger (bước kiểm khởi động #10). Excerpt chép bằng script từ trang đã tải, sau khi bỏ thẻ HTML.

| File | URL | Byte | sha256 |
|---|---|---|---|
| `processors.html` | `https://www.structlog.org/en/25.4.0/processors.html` | 36460 | `d29a3de2f9b3d03475460e4b050fb2bbeaec51908ff3ba21fc55186f0011b0a5` |
| `standard-library.html` | `https://www.structlog.org/en/25.4.0/standard-library.html` | 84923 | `4b9713bb20d2e92fb235205a15dedfa88e1de83f3e3663a0691952da1f65134d` |
| `configuration.html` | `https://www.structlog.org/en/25.4.0/configuration.html` | 32439 | `1c71978da9ff05640c320ad598d0ff4b0f10adbfd021abf33290103e659e5e48` |
| `contextvars.html` | `https://www.structlog.org/en/25.4.0/contextvars.html` | 41573 | `c546984eb975dcca1ea8641ea3cfbecde99bd41c78c87609014a71b4a297f9c9` |

Không commit nguyên các trang HTML; lấy lại bằng URL ở trên và so sha256 (trang có thể đổi sau ngày lấy).

## 1. Giá trị trả về của processor — `processors.html`

> The return value of each processor is passed on to the next one as event_dict until finally the return value of the last processor gets passed into the wrapped logging method. Note structlog only looks at the return value of the last processor. That means that as long as you control the next processor in the chain (the processor that will get your return value passed as an argument), you can return whatever you want.

> It can return one of three types: An Unicode string ( str ), a bytes string ( bytes ), or a bytearray that is passed as the first (and only) positional argument to the underlying logger. A tuple of (args, kwargs) that are passed as log_method(*args, **kwargs) . A dictionary which is passed as log_method(**kwargs) .

Dùng: processor **cuối** của `bo19.observability.log` trả `(args, kwargs)` — `args` = mã sự kiện, `kwargs` = `extra` mang bản ghi đã mask — để `logging.Logger` nhận và chuyển cho handler duy nhất. Không dùng `ProcessorFormatter`: nó là `logging.Formatter` của chính structlog, mà ADR-029 cấm module ngoài `log.py` import `structlog`; `handler.py` không được import nó.

## 2. Nối với `logging` — `standard-library.html`

> render_to_log_args_and_kwargs() : Renders the event dictionary into positional and keyword arguments for logging.Logger logging methods. This is useful if you want to render your log entries entirely within logging . render_to_log_kwargs() : Same as above, but does not support passing positional arguments from structlog loggers to logging.Logger logging methods as positional arguments. structlog positional arguments are still passed to logging under positional_args key of extra keyword argument.

Dùng: không dùng `render_to_log_kwargs` — nó chuyển cả event dict thành `extra` mà không qua bước kiểm kiểu của B2. Processor cuối tự viết, theo mục 1, làm cùng việc nhưng chỉ chuyển bản ghi đã qua mask.

## 3. Điều chưa xác minh bằng tài liệu

- Hai trang `configuration.html` và `contextvars.html` đã tải nhưng B2 không dựa vào: `trace_id` dùng `contextvars` của thư viện chuẩn trong `bo19.observability.trace`, không dùng `structlog.contextvars` — để `handler.py` đọc được `trace_id` mà không import `structlog`.
- Hành vi cụ thể của bản 25.4.0 (không phải của trang tài liệu) được kiểm bằng test chạy thật: `backend/tests/test_observability.py`.
