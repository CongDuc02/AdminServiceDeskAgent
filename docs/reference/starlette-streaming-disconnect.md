# Starlette — `StreamingResponse` khi client ngắt kết nối

- **Nguồn:**
  - `https://raw.githubusercontent.com/encode/starlette/master/starlette/responses.py`
  - `https://raw.githubusercontent.com/encode/starlette/master/starlette/__init__.py`
  - `https://raw.githubusercontent.com/encode/starlette/master/docs/responses.md`
- **Ngày lấy:** 2026-09-13, bằng `curl` trên nhánh `master`. Trang tài liệu `www.starlette.io` không phân giải được tên miền lúc lấy; dùng bản mã nguồn và bản `docs/` trong repo.
- **Phiên bản mà nguồn mô tả:** Starlette **1.6.0** (`__version__ = "1.6.0"` trong `starlette/__init__.py`). Commit gần nhất chạm `starlette/responses.py` là `f04b676e07aaf46a92b6f378ad554cf9edc8fabd` (2026-09-05).
- **Dùng cho:** A-051(4). FastAPI dựng trên Starlette; phiên bản Starlette mà một bản FastAPI cụ thể kéo theo nằm ngoài nguồn này — `[CẦN XÁC MINH]` khi chốt phiên bản.

---

## `StreamingResponse` — `starlette/responses.py`, dòng 244–257

```python
    async def listen_for_disconnect(self, receive: Receive) -> None:
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                break

    async def stream_response(self, send: Send) -> None:
        await send({"type": "http.response.start", "status": self.status_code, "headers": self.raw_headers})
        async for chunk in self.body_iterator:
            if not isinstance(chunk, bytes | memoryview):
                chunk = chunk.encode(self.charset)
            await send({"type": "http.response.body", "body": chunk, "more_body": True})

        await send({"type": "http.response.body", "body": b"", "more_body": False})
```

## `StreamingResponse.__call__` — dòng 267–285 (dòng 259–266 lược)

```python
        spec_version = tuple(map(int, scope.get("asgi", {}).get("spec_version", "2.0").split(".")))

        if spec_version >= (2, 4):
            try:
                await self.stream_response(send)
            except OSError:
                raise ClientDisconnect()
        else:
            async with create_collapsing_task_group() as task_group:

                async def wrap(func: Callable[[], Awaitable[None]]) -> None:
                    await func()
                    task_group.cancel_scope.cancel()

                task_group.start_soon(wrap, partial(self.stream_response, send))
                await wrap(partial(self.listen_for_disconnect, receive))

        if self.background is not None:
            await self.background()
```

## `docs/responses.md`

> ### StreamingResponse
>
> Takes an async generator or a normal generator/iterator and streams the response body.

---

## Nguồn này trả lời gì

- Với máy chủ ASGI báo `spec_version` **dưới 2.4**: khi nhận `http.disconnect`, `listen_for_disconnect` kết thúc và `wrap` gọi `task_group.cancel_scope.cancel()` — tác vụ đang chạy `stream_response`, tức đang lặp `body_iterator`, **bị huỷ**.
- Với `spec_version` **từ 2.4**: không có tác vụ lắng nghe; lần `send` thất bại do `OSError` được đổi thành `ClientDisconnect` — `body_iterator` **không được lặp tiếp**.
- Hai nhánh cho cùng một hệ quả: **việc chạy bên trong body iterator của một `StreamingResponse` không tiếp tục sau khi client ngắt**. Máy chủ ASGI nào báo `spec_version` bao nhiêu nằm ngoài nguồn này.
- Nguồn **không** nói gì về một tác vụ chạy ngoài body iterator — ví dụ tác vụ được tạo riêng rồi chỉ đẩy kết quả vào iterator.
