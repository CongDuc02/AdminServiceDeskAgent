"""Cổng tải file của `api` (B8c, PO 2026-10-13, O1-18): giới hạn số lượt đồng thời, hạn chót tổng mỗi lượt, và response stream từ tệp tạm.

- **`FileGate`** — một `anyio.Semaphore(WV-27)` cho cả tiến trình. Chờ chỗ **không giữ luồng nào** (endpoint là `async`; phần nặng chạy ở threadpool sau khi có chỗ), nên 40 request tải chờ không làm cạn threadpool của các endpoint khác.
  Chờ tối đa WV-28; hết hạn thì `Busy` — router đổi thành `503 FILE_UNAVAILABLE` kèm `Retry-After`.
- **`DeadlineStreamingResponse`** — gửi từng khối của tệp tạm (WV-26), `Content-Length` = kích thước đã kiểm checksum. Hạn chót WV-29 tính từ lúc có chỗ và **bao cả pha stream**: quá hạn thì ngừng gửi, **không gửi phần kết** (response đã bắt đầu nên
  không đổi được mã — server đóng kết nối, client thấy thân ngắn hơn `Content-Length`). Ngắt kết nối bởi client cũng dừng stream. **Ở mọi lối thoát** — xong, quá hạn, client ngắt, lỗi, bị huỷ — tệp tạm được đóng và chỗ được nhả
  (khối `finally` có khiên huỷ), đúng một lần.
Không có hạn chót thì một client đọc cực chậm giữ chỗ vô thời hạn: bốn client như vậy chặn mọi lượt tải khác.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import IO

import anyio
import anyio.to_thread
from starlette.responses import Response
from starlette.types import Receive, Scope, Send

from bo19.config import working_values as wv
from bo19.observability.log import get_logger

log = get_logger("bo19.files")


@dataclass(frozen=True)
class FileFetchLimits:
    """Mặc định là WV-26..30; test dựng giá trị nhỏ để thử hết hạn."""

    concurrent: int = wv.FILE_FETCH_MAX_CONCURRENT
    wait_s: float = wv.FILE_FETCH_WAIT_S
    deadline_s: float = wv.FILE_FETCH_DEADLINE_S
    retry_after_s: int = wv.FILE_FETCH_RETRY_AFTER_S
    chunk_bytes: int = wv.FILE_FETCH_CHUNK_BYTES


class Busy(Exception):
    """Hết WV-28 mà không có chỗ."""


class FileGate:
    def __init__(self, limits: FileFetchLimits) -> None:
        self.limits = limits
        self._slots = anyio.Semaphore(limits.concurrent)
        self.in_flight = 0  # chỉ để test và log; đọc/ghi trong một vòng lặp sự kiện

    async def acquire(self) -> float:
        """Chờ chỗ tối đa `wait_s`. Trả mốc hạn chót (`time.monotonic()`) của lượt này. Quá hạn chờ thì `Busy` (không giữ chỗ nào)."""
        try:
            with anyio.fail_after(self.limits.wait_s):
                await self._slots.acquire()
        except TimeoutError:
            log.warning("FILE_FETCH_BUSY", concurrent=self.limits.concurrent)
            raise Busy from None
        self.in_flight += 1
        return time.monotonic() + self.limits.deadline_s

    def release(self) -> None:
        self.in_flight -= 1
        self._slots.release()


class DeadlineStreamingResponse(Response):
    def __init__(self, file: IO[bytes], *, size: int, media_type: str, headers: dict[str, str], deadline: float, chunk_bytes: int, gate: FileGate) -> None:
        super().__init__(content=None, status_code=200, headers=headers, media_type=media_type)
        self.headers["content-length"] = str(size)
        self._file, self._deadline, self._chunk, self._gate = file, deadline, chunk_bytes, gate
        self._closed = False

    def _finish(self) -> None:
        if not self._closed:
            self._closed = True
            try:
                self._file.close()
            finally:
                self._gate.release()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            with anyio.move_on_after(max(self._deadline - time.monotonic(), 0)) as deadline_scope:
                await send({"type": "http.response.start", "status": self.status_code, "headers": self.raw_headers})
                async with anyio.create_task_group() as tg:
                    async def watch_disconnect() -> None:
                        while (await receive())["type"] != "http.disconnect":
                            pass
                        tg.cancel_scope.cancel()

                    tg.start_soon(watch_disconnect)
                    while True:
                        chunk = await anyio.to_thread.run_sync(self._file.read, self._chunk)
                        if not chunk:
                            break
                        await send({"type": "http.response.body", "body": chunk, "more_body": True})
                    await send({"type": "http.response.body", "body": b"", "more_body": False})
                    tg.cancel_scope.cancel()
            if deadline_scope.cancelled_caught:
                log.warning("FILE_FETCH_DEADLINE")  # cắt kết nối: không gửi phần kết
        finally:
            with anyio.CancelScope(shield=True):
                self._finish()
