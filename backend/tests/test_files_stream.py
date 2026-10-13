"""Tải file qua tệp tạm (B8c; ADR-014; PO 2026-10-13, O1-18) — `storage.fetch_verified`, `FileGate` và `DeadlineStreamingResponse`, trên PostgreSQL và SeaweedFS 4.47 THẬT, qua ASGI thô (để điều khiển tốc độ đọc của "client").

Điều được chứng minh, nói bằng hành vi:
- **bộ nhớ không theo kích thước file:** một tiến trình riêng tải file 8 MiB và 64 MiB — mức tăng RSS đỉnh của hai lần chênh nhau dưới 3 MiB và lần 64 MiB dưới 10 MiB (bộ đệm cả file sẽ tăng ≥ 64 MiB);
- **tệp tạm bị xoá ở mọi lối thoát:** thành công rồi đóng, checksum lệch, object mất, quá trần, storage trả nhiều hơn đã commit, storage đứt giữa chừng, hết hạn chót, và ở lớp response: client ngắt, `send` ném lỗi, hết hạn chót giữa stream, hết hạn chót trước khi bắt đầu — không còn file descriptor tới tệp tạm đã xoá;
- **không byte nào ra khi checksum lệch** (ở lớp response: không có `http.response.start`);
- **hạn chót tổng (WV-29) bao cả pha stream:** client đọc cực chậm bị cắt ĐÚNG ở hạn chót — response không bao giờ được hoàn tất (`more_body = False` không được gửi) — và chỗ được trả; bốn client chậm giữ hết chỗ thì lượt thứ năm nhận 503 sau đúng thời gian chờ (WV-28) chứ không chờ tới hạn chót của họ, rồi sau khi họ bị cắt thì lượt kế tiếp được phục vụ;
- **`503 FILE_UNAVAILABLE` hai dạng:** "bận" có `Retry-After`; file hỏng/mất/hết hạn khi tải thì KHÔNG có;
- **chỗ không rò:** mọi lối lỗi trước response (từ chối quyền, không tồn tại, file hỏng) đều nhả chỗ — chạy 20 lượt lỗi liên tiếp với `concurrent = 1` mà lượt hợp lệ sau đó vẫn được phục vụ.

Cần BO19_TEST_PG_SUPERUSER_DSN và BO19_TEST_S3_ENDPOINT. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_files_stream -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest import mock

from bo19.api.files_gate import FileFetchLimits
from bo19.config import working_values as wv
from bo19.object_storage import StorageError
from bo19.tool_layer import storage as st
from tests.s3_support import ENDPOINT
from tests.test_files_api import API, FilesBase

MIB = 1024 * 1024


def deleted_tmp_fds() -> int:
    """Số file descriptor của tiến trình này trỏ tới một tệp tạm đã xoá tên (`TemporaryFile` vô danh)."""
    tmp, n = tempfile.gettempdir(), 0
    for fd in os.listdir("/proc/self/fd"):
        try:
            target = os.readlink(f"/proc/self/fd/{fd}")
        except OSError:
            continue
        if target.startswith(tmp) and "(deleted)" in target:
            n += 1
    return n


class Spy:
    """Bọc `ObjectStorage`: ghi lại kích thước khối đã yêu cầu và số khối đã trả; cho phép chèn lỗi giữa chừng."""

    def __init__(self, inner, *, fail_after: int | None = None, extra: bytes = b"") -> None:
        self.inner, self.fail_after, self.extra = inner, fail_after, extra
        self.requested: list[int] = []
        self.yielded = 0
        self.bucket = inner.bucket

    def get_chunks(self, key, chunk_size):
        self.requested.append(chunk_size)
        for chunk in self.inner.get_chunks(key, chunk_size):
            if self.fail_after is not None and self.yielded >= self.fail_after:
                raise StorageError("STORAGE_UNAVAILABLE")
            self.yielded += 1
            yield chunk
        if self.extra:
            yield self.extra

    def __getattr__(self, name):
        return getattr(self.inner, name)


class FetchVerified(FilesBase):
    def put_bytes(self, data: bytes) -> str:
        key = f"renders/{uuid.uuid4()}/v.pdf"
        self.put(key, data, "RENDER_PDF")
        return key

    def fetch(self, key, storage=None, **kw):
        kw.setdefault("max_bytes", 200 * MIB)
        return st.fetch_verified(self.pool, storage or self.storage, key, **kw)

    def test_tra_dung_byte_da_tua_ve_dau_va_kich_thuoc(self):
        data = os.urandom(1_000_003)
        key = self.put_bytes(data)
        f, size = self.fetch(key, chunk_bytes=64 * 1024)
        with f:
            self.assertEqual((f.tell(), size), (0, len(data)))
            self.assertEqual(f.read(), data)

    def test_tai_theo_khoi_dung_kich_thuoc_khoi_duoc_yeu_cau(self):
        spy = Spy(self.storage)
        key = self.put_bytes(b"x" * 5000)
        f, _ = self.fetch(key, spy, chunk_bytes=1024)
        f.close()
        self.assertEqual(spy.requested, [1024])
        self.assertGreaterEqual(spy.yielded, 5)  # nhiều khối, không phải một lần đọc cả file
        f, _ = self.fetch(key, spy)
        f.close()
        self.assertEqual(spy.requested[-1], wv.FILE_FETCH_CHUNK_BYTES)  # mặc định WV-26

    def test_khong_ro_tep_tam_o_moi_loi_thoat(self):
        base = deleted_tmp_fds()
        names_before = set(os.listdir(tempfile.gettempdir()))
        good = self.put_bytes(b"abc" * 1000)
        f, _ = self.fetch(good)
        self.assertEqual(deleted_tmp_fds(), base + 1)  # đang mở: đúng một tệp
        f.close()
        self.assertEqual(deleted_tmp_fds(), base)
        bad_hash = self.put_bytes(b"abc" * 1000)
        self.raw.put_object(Bucket=self.bucket, Key=bad_hash, Body=b"abd" * 1000)
        missing = self.put_bytes(b"x")
        self.raw.delete_object(Bucket=self.bucket, Key=missing)
        big = self.put_bytes(b"y" * 5000)
        grown = self.put_bytes(b"z" * 3000)
        cases = {
            "lệch checksum": lambda: self.fetch(bad_hash),
            "mất object": lambda: self.fetch(missing),
            "quá trần": lambda: self.fetch(big, max_bytes=100),
            "chưa commit": lambda: self.fetch("khong/co.pdf"),
            "storage trả nhiều hơn đã commit": lambda: self.fetch(grown, Spy(self.storage, extra=b"them"), chunk_bytes=1000),
            "storage đứt giữa chừng": lambda: self.fetch(big, Spy(self.storage, fail_after=1), chunk_bytes=1000),
            "hết hạn chót": lambda: self.fetch(big, deadline=time.monotonic() - 1, chunk_bytes=1000),
        }
        for name, call in cases.items():
            with self.assertRaises(st.FileUnavailable, msg=name):
                call()
            self.assertEqual(deleted_tmp_fds(), base, name)
        self.assertEqual(set(os.listdir(tempfile.gettempdir())) - names_before, set())  # tệp tạm VÔ DANH: không có tên nào xuất hiện trên đĩa, dù chỉ thoáng qua rồi bị xoá sót

    def test_ly_do_tung_loai_chi_de_log(self):
        key = self.put_bytes(b"q" * 4000)
        for name, kw, expected in (("cut", dict(storage=Spy(self.storage, fail_after=1), chunk_bytes=1000), "STORAGE_UNAVAILABLE"), ("deadline", dict(deadline=time.monotonic() - 1, chunk_bytes=1000), "DEADLINE"),
                                   ("grown", dict(storage=Spy(self.storage, extra=b"x"), chunk_bytes=1000), "CHECKSUM_MISMATCH"), ("trần", dict(max_bytes=10), "TOO_LARGE")):
            with self.assertRaises(st.FileUnavailable, msg=name) as cm:
                self.fetch(key, **kw)
            self.assertEqual(cm.exception.reason, expected, name)

    def test_vuot_do_dai_da_commit_thi_dung_som_khong_doc_not(self):
        key = self.put_bytes(b"a" * 2000)
        self.raw.put_object(Bucket=self.bucket, Key=key, Body=b"a" * 200_000)  # object bị thay bằng bản dài hơn nhiều
        spy = Spy(self.storage)
        with self.assertRaises(st.FileUnavailable):
            self.fetch(key, spy, chunk_bytes=1000)
        self.assertLess(spy.yielded, 10)  # dừng ngay khi vượt, không đọc hết 200 khối

    def test_rss_khong_tang_theo_kich_thuoc_file(self):
        small, large = self.put_bytes(os.urandom(8 * MIB)), self.put_bytes(os.urandom(64 * MIB))
        env = {**os.environ, "PROBE_DSN": self.db.dsn("bo19_app"), "PROBE_BUCKET": self.bucket, "PYTHONPATH": "src" + os.pathsep + "."}
        probe = str(Path(__file__).with_name("fetch_rss_probe.py"))

        def run(key: str) -> dict:
            out = subprocess.run([sys.executable, probe, key], capture_output=True, text=True, env=env, timeout=300, cwd=str(Path(__file__).resolve().parents[1]))
            self.assertEqual(out.returncode, 0, out.stderr[-500:])
            return json.loads(out.stdout.strip().splitlines()[-1])

        a, b = run(small), run(large)
        self.assertEqual((a["size"], b["size"]), (8 * MIB, 64 * MIB))
        self.assertLess(b["delta_mib"], 10, (a, b))
        self.assertLess(abs(b["delta_mib"] - a["delta_mib"]), 3, (a, b))


@unittest.skipUnless(ENDPOINT, "cần BO19_TEST_S3_ENDPOINT")
class Stream(FilesBase, unittest.IsolatedAsyncioTestCase):
    """Qua ASGI thô trong MỘT vòng lặp sự kiện: điều khiển tốc độ đọc và lúc ngắt của "client"."""

    def limits(self, **kw) -> FileFetchLimits:
        return FileFetchLimits(**{"concurrent": 4, "wait_s": 1.0, "deadline_s": 3.0, "retry_after_s": 5, "chunk_bytes": 4096, **kw})

    def setUp(self):
        super().setUp()
        self.loop_events: list = []

    async def call(self, doc: uuid.UUID, render: uuid.UUID, who: uuid.UUID, *, fmt="pdf", send_delay: float = 0.0, disconnect_after: int | None = None, send_error_after: int | None = None) -> dict:
        """Một lời gọi ASGI thô. Trả `{status, headers, body, ended, started_at, finished_at}`; `ended` = đã nhận `more_body=False`."""
        cookie = self.as_user(who)["Cookie"].encode()
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "scheme": "https", "path": f"{API}/documents/{doc}/renders/{render}/file", "raw_path": b"",
                 "query_string": f"format={fmt}".encode(), "root_path": "", "headers": [(b"cookie", cookie), (b"host", b"testserver")], "client": (self.ip, 50000), "server": ("testserver", 443)}
        got = {"status": None, "headers": {}, "body": b"", "ended": False, "chunks": 0}
        gone = asyncio.Event()
        sent = 0
        first = True

        async def receive():
            nonlocal first
            if first:
                first = False
                return {"type": "http.request", "body": b"", "more_body": False}
            await gone.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            nonlocal sent
            if message["type"] == "http.response.start":
                got["status"], got["headers"] = message["status"], {k.decode().lower(): v.decode() for k, v in message["headers"]}
                return
            if send_delay:
                await asyncio.sleep(send_delay)  # client đọc chậm: mỗi khối mất ngần này
            if send_error_after is not None and sent >= send_error_after:
                raise ConnectionResetError
            got["body"] += message.get("body", b"")
            got["chunks"] += 1
            sent += 1
            if not message.get("more_body", False):
                got["ended"] = True
            if disconnect_after is not None and sent >= disconnect_after:
                gone.set()

        got["started_at"] = time.monotonic()
        try:
            await self.app(scope, receive, send)
        except BaseException:  # noqa: BLE001 — `send` ném trong task group → ExceptionGroup, như uvicorn thật gặp khi client biến mất
            got["send_error"] = True
        got["finished_at"] = time.monotonic()
        return got

    @property
    def gate(self):
        return self.app.state.file_gate

    def big(self, kib: int = 200) -> tuple[uuid.UUID, uuid.UUID, bytes]:
        data = os.urandom(kib * 1024)
        did, rid = self.make_render(pdf=data)
        return did, rid, data

    async def test_stream_day_du_content_length_dung_va_ket_thuc_sach(self):
        self.rebuild(self.storage, self.limits())
        did, rid, data = self.big()
        base = deleted_tmp_fds()
        r = await self.call(did, rid, self.officer)
        self.assertEqual((r["status"], r["body"], r["ended"]), (200, data, True))
        self.assertEqual(r["headers"]["content-length"], str(len(data)))
        self.assertGreater(r["chunks"], 40)  # 200 KiB / 4 KiB: stream nhiều khối
        self.assertEqual((self.gate.in_flight, deleted_tmp_fds()), (0, base))

    async def test_client_doc_cuc_cham_bi_cat_dung_han_chot_va_cho_duoc_tra(self):
        self.rebuild(self.storage, self.limits(deadline_s=1.5))
        did, rid, data = self.big()
        base = deleted_tmp_fds()
        r = await self.call(did, rid, self.officer, send_delay=0.25)  # 50 khối × 0,25 s ≈ 12 s nếu không có hạn chót
        elapsed = r["finished_at"] - r["started_at"]
        self.assertGreaterEqual(elapsed, 1.3)
        self.assertLess(elapsed, 4.0)  # cắt ở ≈ 1,5 s, không phải 12 s
        self.assertFalse(r["ended"])  # không bao giờ gửi phần kết: client thấy thân ngắn hơn Content-Length
        self.assertLess(len(r["body"]), len(data))
        self.assertEqual((self.gate.in_flight, deleted_tmp_fds()), (0, base))
        ok = await self.call(did, rid, self.officer)  # chỗ đã được trả
        self.assertEqual((ok["status"], ok["body"]), (200, data))

    async def test_bon_client_cham_khong_chan_luot_thu_nam_qua_han_chot(self):
        self.rebuild(self.storage, self.limits(concurrent=4, wait_s=1.0, deadline_s=3.0))
        did, rid, data = self.big()
        slow = [asyncio.create_task(self.call(did, rid, self.officer, send_delay=0.5)) for _ in range(4)]
        for _ in range(60):  # chờ bốn lượt giữ hết chỗ
            await asyncio.sleep(0.1)
            if self.gate.in_flight == 4:
                break
        self.assertEqual(self.gate.in_flight, 4)
        fifth = await self.call(did, rid, self.officer)
        waited = fifth["finished_at"] - fifth["started_at"]
        self.assertEqual(fifth["status"], 503)
        self.assertGreaterEqual(waited, 0.9)  # chờ đủ WV-28
        self.assertLess(waited, 2.5)  # và dừng ở đó — không chờ tới hạn chót 3 s của bốn client chậm
        self.assertEqual(fifth["headers"]["retry-after"], "5")
        body = json.loads(fifth["body"])
        self.assertEqual(body["error_code"], "FILE_UNAVAILABLE")
        results = await asyncio.gather(*slow)
        self.assertTrue(all(not r["ended"] for r in results))  # cả bốn bị cắt ở hạn chót
        sixth = await self.call(did, rid, self.officer)
        self.assertEqual((sixth["status"], sixth["body"]), (200, data))  # sau khi bị cắt, chỗ trống lại
        self.assertEqual(self.gate.in_flight, 0)

    async def test_503_ban_co_retry_after_con_503_file_hong_thi_khong(self):
        self.rebuild(self.storage, self.limits(concurrent=1, wait_s=0.5, deadline_s=2.0))
        did, rid, _ = self.big()
        broken_doc, broken_render = self.make_render()
        self.raw.delete_object(Bucket=self.bucket, Key=f"renders/{broken_doc}/h.pdf")
        slow = asyncio.create_task(self.call(did, rid, self.officer, send_delay=0.5))
        for _ in range(40):
            await asyncio.sleep(0.05)
            if self.gate.in_flight == 1:
                break
        busy = await self.call(did, rid, self.officer)
        self.assertEqual((busy["status"], busy["headers"].get("retry-after")), (503, "5"))
        await slow
        broken = await self.call(broken_doc, broken_render, self.officer)
        self.assertEqual(broken["status"], 503)
        self.assertNotIn("retry-after", broken["headers"])  # file mất: không phải "thử lại sau"
        self.assertEqual(json.loads(broken["body"])["error_code"], "FILE_UNAVAILABLE")

    async def test_client_ngat_giua_stream_dong_tep_va_nha_cho(self):
        self.rebuild(self.storage, self.limits(concurrent=1))
        did, rid, data = self.big()
        base = deleted_tmp_fds()
        r = await self.call(did, rid, self.officer, disconnect_after=3)
        self.assertFalse(r["ended"])
        self.assertLess(len(r["body"]), len(data))
        self.assertEqual((self.gate.in_flight, deleted_tmp_fds()), (0, base))
        self.assertEqual((await self.call(did, rid, self.officer))["body"], data)  # concurrent = 1 mà lượt sau vẫn vào được

    async def test_send_nem_loi_van_dong_tep_va_nha_cho(self):
        self.rebuild(self.storage, self.limits(concurrent=1))
        did, rid, data = self.big()
        base = deleted_tmp_fds()
        r = await self.call(did, rid, self.officer, send_error_after=2)
        self.assertTrue(r.get("send_error"))
        self.assertEqual((self.gate.in_flight, deleted_tmp_fds()), (0, base))
        self.assertEqual((await self.call(did, rid, self.officer))["body"], data)

    async def test_checksum_lech_khong_co_byte_nao_ra_va_khong_ro_cho(self):
        self.rebuild(self.storage, self.limits(concurrent=1))
        did, rid, data = self.big()
        self.raw.put_object(Bucket=self.bucket, Key=f"renders/{did}/h.pdf", Body=data[:-1] + b"X")
        base = deleted_tmp_fds()
        r = await self.call(did, rid, self.officer)
        self.assertEqual((r["status"], r["body"] and json.loads(r["body"])["error_code"]), (503, "FILE_UNAVAILABLE"))
        self.assertNotIn(b"%PDF", r["body"])
        self.assertEqual(r["chunks"], 1)  # chỉ thân lỗi JSON, không một khối nào của file
        self.assertEqual((self.gate.in_flight, deleted_tmp_fds()), (0, base))

    async def test_het_han_chot_trong_pha_tai_la_503_khong_retry_after(self):
        self.rebuild(self.storage, self.limits(concurrent=1, deadline_s=0.0))
        did, rid, _ = self.big()
        base = deleted_tmp_fds()
        r = await self.call(did, rid, self.officer)
        self.assertEqual(r["status"], 503)
        self.assertNotIn("retry-after", r["headers"])
        self.assertEqual((self.gate.in_flight, deleted_tmp_fds()), (0, base))

    async def test_loi_truoc_response_deu_nha_cho_hai_muoi_luot(self):
        """Từ chối quyền, không tồn tại, file hỏng — hai mươi lượt lỗi liên tiếp với `concurrent = 1`; lượt hợp lệ sau đó vẫn được phục vụ."""
        self.rebuild(self.storage, self.limits(concurrent=1, wait_s=0.3))
        did, rid, data = self.big()
        draft_doc, draft_render = self.make_render(kind="DRAFT")
        for i in range(20):
            if i % 3 == 0:
                r = await self.call(draft_doc, draft_render, self.creator)  # PERMISSION_DENIED
                self.assertEqual(r["status"], 403)
            elif i % 3 == 1:
                r = await self.call(did, uuid.uuid4(), self.officer)  # NOT_FOUND
                self.assertEqual(r["status"], 404)
            else:
                r = await self.call(did, rid, self.other)  # người lạ: NOT_FOUND
                self.assertEqual(r["status"], 404)
            self.assertEqual(self.gate.in_flight, 0, i)
        self.assertEqual((await self.call(did, rid, self.officer))["body"], data)

    async def test_nhieu_luot_dong_thoi_khong_vuot_tran(self):
        self.rebuild(self.storage, self.limits(concurrent=3, wait_s=60.0, deadline_s=120.0))
        did, rid, data = self.big(100)
        peak = 0

        async def watch():
            nonlocal peak
            while True:
                peak = max(peak, self.gate.in_flight)
                await asyncio.sleep(0.005)

        w = asyncio.create_task(watch())
        results = await asyncio.gather(*[self.call(did, rid, self.officer, send_delay=0.02) for _ in range(8)])
        w.cancel()
        self.assertEqual([(r["status"], r["body"] == data) for r in results], [(200, True)] * 8)
        self.assertLessEqual(peak, 3)
        self.assertGreaterEqual(peak, 2)  # có đồng thời thật, không phải chạy tuần tự
        self.assertEqual(self.gate.in_flight, 0)

    async def test_ghi_audit_loi_thi_dong_tep_khong_giao_file(self):
        """`audit_event` là điều kiện để giao file: không ghi được dấu vết thì tệp đã tải bị đóng, không ai nhận, chỗ được nhả."""
        self.rebuild(self.storage, self.limits(concurrent=1))
        did, rid, data = self.big(50)
        base = deleted_tmp_fds()
        with mock.patch("bo19.tool_layer.endpoint_ops.files._audit", side_effect=RuntimeError("audit hỏng")):
            r = await self.call(did, rid, self.officer)
        self.assertEqual(r["status"], 500)
        self.assertNotIn(b"%PDF", r["body"])
        self.assertEqual((self.gate.in_flight, deleted_tmp_fds()), (0, base))
        self.assertEqual((await self.call(did, rid, self.officer))["body"], data)

    async def test_tai_xong_dung_luc_het_han_khong_bat_dau_response_bi_cat(self):
        """Pha tải kết thúc sau hạn chót (ở đây: bộ tải bỏ qua `deadline`) thì router trả 503 trước khi gửi byte nào, đóng tệp đã tải và nhả chỗ."""
        self.rebuild(self.storage, self.limits(concurrent=1, deadline_s=0.3))
        did, rid, data = self.big(50)
        real = st.fetch_verified

        def slow(*a, **kw):
            kw["deadline"] = None  # không tự kiểm hạn chót
            out = real(*a, **kw)
            time.sleep(0.5)
            return out

        base = deleted_tmp_fds()
        with mock.patch("bo19.tool_layer.endpoint_ops.files.store.fetch_verified", slow):
            r = await self.call(did, rid, self.officer)
        self.assertEqual(r["status"], 503)
        self.assertNotIn("retry-after", r["headers"])
        self.assertNotIn(b"%PDF", r["body"])
        self.assertEqual((self.gate.in_flight, deleted_tmp_fds()), (0, base))

    async def test_mac_dinh_la_wv_26_den_30(self):
        d = FileFetchLimits()
        self.assertEqual((d.concurrent, d.wait_s, d.deadline_s, d.retry_after_s, d.chunk_bytes), (4, 15, 60, 5, 256 * 1024))
        self.assertEqual((wv.FILE_FETCH_MAX_CONCURRENT, wv.FILE_FETCH_WAIT_S, wv.FILE_FETCH_DEADLINE_S), (4, 15, 60))


if __name__ == "__main__":
    unittest.main()
