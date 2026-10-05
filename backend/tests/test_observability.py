"""Test gói `bo19.observability` — B2. AC-1.8 ở dạng **phần mask, test đơn vị**.

AC-1.8 trọn vẹn (một dòng log thật của một request chạy từ đầu tới cuối, thấy `[PER]`/`[RES]` thay giá trị) chỉ chứng minh được
ở lần chạy AC-1.1 — lúc đó mới có request thật. B2 chưa chứng minh phần đó, và không tuyên bố đã chứng minh.

Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_observability -v   (cần structlog — requirements-linux.lock)
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import io
import json
import logging
import re
import unittest
from pathlib import Path

from bo19.domain.sensitivity import SlotSensitivity
from bo19.observability import handler as obs_handler
from bo19.observability import trace
from bo19.observability.log import LogUsageError, configure_logging, get_logger
from bo19.observability.masking import Sensitive

SRC = Path(__file__).resolve().parents[1] / "src" / "bo19"
UUID4 = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
# Giá trị mà không được xuất hiện NGUYÊN VĂN, hay một mảnh của nó, ở bất kỳ chỗ nào của đầu ra.
PER_VALUE = "Nguyễn Văn Thử"
RES_VALUE = "001099012345"


class LogCase(unittest.TestCase):
    def setUp(self) -> None:
        self.out = io.StringIO()
        self.handler = configure_logging(self.out)
        self.addCleanup(logging.getLogger().removeHandler, self.handler)

    def lines(self) -> list[dict]:
        return [json.loads(x) for x in self.out.getvalue().splitlines()]

    def last(self) -> dict:
        return self.lines()[-1]


class Mask(LogCase):
    """AC-1.8 — phần mask. `INT` giữ, `PER` → `[PER]`, `RES` → `[RES]`."""

    def test_int_khong_mask(self):
        get_logger("bo19.test").info("SLOT_READ", value=Sensitive("Phòng Hành chính", SlotSensitivity.INT))
        self.assertEqual(self.last()["value"], "Phòng Hành chính")

    def test_per_thanh_nhan_va_khong_lo_manh_nao(self):
        get_logger("bo19.test").info("SLOT_READ", value=Sensitive(PER_VALUE, SlotSensitivity.PER))
        raw = self.out.getvalue()
        self.assertEqual(self.last()["value"], "[PER]")
        for piece in (PER_VALUE, "Nguyễn", "Thử"):  # cả giá trị lẫn các mảnh có nghĩa của nó
            self.assertNotIn(piece, raw, piece)
        self.assertNotIn(f'"{len(PER_VALUE)}"', raw)  # không log độ dài

    def test_res_thanh_nhan(self):
        get_logger("bo19.test").info("SLOT_READ", slot_name="bearer_national_id", value=Sensitive(RES_VALUE, SlotSensitivity.RES))
        rec = self.last()
        self.assertEqual(rec["value"], "[RES]")
        self.assertEqual(rec["slot_name"], "bearer_national_id")  # tên slot là metadata cấu trúc — giữ
        self.assertNotIn(RES_VALUE, self.out.getvalue())
        self.assertNotIn(RES_VALUE[:4], self.out.getvalue())

    def test_input_khong_phai_slot_mask_nhu_res(self):
        get_logger("bo19.test").info("INPUT_SEEN", chat_text=Sensitive.unclassified(f"CCCD của tôi là {RES_VALUE}"))
        self.assertEqual(self.last()["chat_text"], "[RES]")
        self.assertNotIn(RES_VALUE, self.out.getvalue())

    def test_str_va_repr_cua_sensitive_khong_chua_gia_tri(self):
        for s in SlotSensitivity:
            v = Sensitive("GIA_TRI_BI_MAT", s)
            self.assertNotIn("GIA_TRI_BI_MAT", str(v))
            self.assertNotIn("GIA_TRI_BI_MAT", repr(v))
            self.assertNotIn("GIA_TRI_BI_MAT", f"{v}")

    def test_bind_van_mask(self):
        log = get_logger("bo19.test").bind(owner=Sensitive(PER_VALUE, SlotSensitivity.PER))
        log.info("OWNED")
        log.warning("OWNED_AGAIN")
        self.assertEqual([r["owner"] for r in self.lines()], ["[PER]", "[PER]"])
        self.assertNotIn(PER_VALUE, self.out.getvalue())

    def test_exception_chi_mang_kieu_khong_mang_thong_diep(self):
        get_logger("bo19.test").error("TOOL_FAILED", exc=ValueError(f"CCCD {RES_VALUE} không hợp lệ"))
        rec = self.last()
        self.assertEqual(rec["error_type"], "ValueError")
        self.assertNotIn(RES_VALUE, self.out.getvalue())

    def test_buoc_mask_nam_trong_chuoi_truoc_handler(self):
        """ADR-029: mask là một bước TRONG chuỗi, trước bước xuất. Bắt bản ghi ngay khi tới logging — chưa qua handler mask —
        và đòi nó đã không còn giá trị gốc (không dựa vào lớp phòng thủ ở handler)."""
        seen: list[logging.LogRecord] = []

        class Spy(logging.Handler):
            def emit(self, record):
                seen.append(record)

        spy = Spy()
        lg = logging.getLogger("bo19.chain")
        lg.addHandler(spy)
        self.addCleanup(lg.removeHandler, spy)
        get_logger("bo19.chain").info("X", per=Sensitive(PER_VALUE, SlotSensitivity.PER), res=Sensitive(RES_VALUE, SlotSensitivity.RES),
                                      keep=Sensitive("công khai", SlotSensitivity.INT))
        event = seen[0].bo19_event
        self.assertEqual((event["per"], event["res"], event["keep"]), ("[PER]", "[RES]", "công khai"))
        self.assertNotIn(PER_VALUE + RES_VALUE, repr(event))

    def test_sensitive_lot_qua_buoc_mask_van_bi_mask_o_handler(self):
        """Phòng thủ chiều sâu: nếu một `Sensitive` tới được handler mà chưa qua chuỗi processor, handler vẫn không in giá trị."""
        rec = logging.LogRecord("bo19.test", logging.INFO, __file__, 1, "X", None, None)
        rec.bo19_event = {"event": "X", "value": Sensitive(RES_VALUE, SlotSensitivity.RES)}
        self.handler.handle(rec)
        self.assertEqual(self.last()["value"], "[RES]")
        self.assertNotIn(RES_VALUE, self.out.getvalue())

    def test_vat_la_khong_duoc_serialize_nguyen(self):
        class Secret:
            def __repr__(self):
                return RES_VALUE
        rec = logging.LogRecord("bo19.test", logging.INFO, __file__, 1, "X", None, None)
        rec.bo19_event = {"event": "X", "thing": Secret()}
        self.handler.handle(rec)
        self.assertEqual(self.last()["thing"], "[UNSERIALIZABLE:Secret]")
        self.assertNotIn(RES_VALUE, self.out.getvalue())


class ThuVienBenThuBa(LogCase):
    def test_bo_noi_dung_chi_giu_ten_logger_muc_va_kieu_loi(self):
        logging.getLogger("httpx").info("GET https://example.invalid/?token=BI_MAT_CUA_THU_VIEN 200")
        rec = self.last()
        self.assertEqual((rec["component"], rec["level"], rec["message"]), ("httpx", "INFO", obs_handler.THIRD_PARTY_MESSAGE))
        self.assertNotIn("BI_MAT_CUA_THU_VIEN", self.out.getvalue())
        self.assertNotIn("token", self.out.getvalue())

    def test_loi_cua_thu_vien_chi_con_kieu(self):
        try:
            raise KeyError(f"cccd={RES_VALUE}")
        except KeyError:
            logging.getLogger("psycopg").exception("lỗi có %s", RES_VALUE)
        rec = self.last()
        self.assertEqual(rec["error_type"], "KeyError")
        self.assertEqual(rec["level"], "ERROR")
        self.assertNotIn(RES_VALUE, self.out.getvalue())

    def test_args_cua_ban_ghi_khong_duoc_noi_vao_dau_ra(self):
        logging.getLogger("uvicorn.access").info('%s - "%s %s HTTP/%s" %d', "10.0.0.1", "GET", "/api/x?cccd=1", "1.1", 200)
        self.assertNotIn("10.0.0.1", self.out.getvalue())
        self.assertNotIn("cccd", self.out.getvalue())


class MotHandlerDuyNhat(LogCase):
    def test_goi_cai_dat_nhieu_lan_van_chi_mot_handler(self):
        for _ in range(3):
            configure_logging(io.StringIO())
        handlers = obs_handler.root_handlers()
        self.assertEqual(len(handlers), 1)
        self.assertIsInstance(handlers[0], obs_handler.MaskedJsonHandler)

    def test_handler_la_lop_cua_observability_va_handler_khac_bi_bo(self):
        logging.getLogger().addHandler(logging.StreamHandler(io.StringIO()))
        self.assertEqual(len(obs_handler.root_handlers()), 2)
        configure_logging(io.StringIO())
        self.assertEqual(len(obs_handler.root_handlers()), 1)


class DinhDang(LogCase):
    def test_schema_moi_dong(self):
        with trace.trace_scope() as tid:
            get_logger("bo19.startup").info("STARTUP_OK", steps=11)
        rec = self.last()
        self.assertEqual(list(rec)[:5], ["timestamp", "level", "component", "trace_id", "message"])
        self.assertEqual((rec["level"], rec["component"], rec["message"], rec["steps"]), ("INFO", "bo19.startup", "STARTUP_OK", 11))
        self.assertEqual(rec["trace_id"], tid)
        self.assertRegex(rec["timestamp"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")  # UTC, hậu tố Z

    def test_timestamp_la_utc(self):
        rec = logging.LogRecord("c", logging.INFO, __file__, 1, "x", None, None)
        rec.created = 1_790_000_000.5  # 2026-09-21T14:13:20.500Z (kiểm độc lập bằng date -u -d @1790000000)
        self.assertEqual(obs_handler._utc_iso(rec.created), "2026-09-21T14:13:20.500Z")

    def test_moi_dong_la_mot_dong_json(self):
        get_logger("bo19.test").info("A", note="một\ndòng\nbị xuống dòng")
        get_logger("bo19.test").info("B")
        self.assertEqual(len(self.out.getvalue().splitlines()), 2)

    def test_tieng_viet_khong_bi_escape(self):
        get_logger("bo19.test").info("A", unit="Phòng Hành chính")
        self.assertIn("Phòng Hành chính", self.out.getvalue())

    def test_enum_ghi_bang_gia_tri(self):
        get_logger("bo19.test").info("A", sensitivity=SlotSensitivity.PER)
        self.assertEqual(self.last()["sensitivity"], "PER")


class Trace(LogCase):
    def test_trace_id_la_uuid_v4_chu_thuong(self):
        for _ in range(50):
            self.assertRegex(trace.new_trace_id(), UUID4)

    def test_moi_scope_mot_id_moi_va_tra_lai_gia_tri_cu(self):
        self.assertIsNone(trace.current_trace_id())
        with trace.trace_scope() as a:
            with trace.trace_scope() as b:
                self.assertNotEqual(a, b)
                self.assertEqual(trace.current_trace_id(), b)
            self.assertEqual(trace.current_trace_id(), a)
        self.assertIsNone(trace.current_trace_id())

    def test_ngoai_scope_trace_id_la_null(self):
        get_logger("bo19.test").info("A")
        self.assertIsNone(self.last()["trace_id"])

    def test_dong_cua_thu_vien_cung_mang_trace_id(self):
        with trace.trace_scope() as tid:
            logging.getLogger("httpx").info("x")
        self.assertEqual(self.last()["trace_id"], tid)

    def test_khong_nhan_trace_id_sai_khuon(self):
        for bad in ("", "abc", "550E8400-E29B-41D4-A716-446655440000", "550e8400e29b41d4a716446655440000",
                    "550e8400-e29b-11d4-a716-446655440000"):  # hoa; không gạch nối; không phải v4
            with self.assertRaises(ValueError, msg=bad), trace.trace_scope(bad):
                pass
        with trace.trace_scope("550e8400-e29b-41d4-a716-446655440000") as ok:
            self.assertEqual(ok, "550e8400-e29b-41d4-a716-446655440000")


class KhuonApi(LogCase):
    """API log chỉ nhận mã sự kiện và trường có kiểu (06-structure.md, mục Nghĩa vụ kế thừa)."""

    def test_su_kien_phai_la_ma(self):
        log = get_logger("bo19.test")
        for bad in ("văn bản tự do", "lowercase", "Có dấu cách", "", "A-B", f"user {RES_VALUE}"):
            with self.assertRaises(LogUsageError, msg=bad):
                log.info(bad)
        log.info("MA_HOP_LE_01")

    def test_truong_phai_co_kieu(self):
        log = get_logger("bo19.test")
        for bad in ({"x": object()}, {"x": [1, 2]}, {"x": {"a": 1}}, {"x": b"bytes"}, {"x": "a" * 301}):
            with self.assertRaises(LogUsageError, msg=str(bad)[:30]):
                log.info("MA", **bad)

    def test_ten_truong_khong_duoc_de_len_khoa_cua_schema(self):
        log = get_logger("bo19.test")
        for key in ("trace_id", "level", "component", "message", "timestamp", "event", "exc", "error_type", "Hoa", "1x"):
            with self.assertRaises(LogUsageError, msg=key):
                log.info("MA", **{key: 1})


class QuetVanBan(unittest.TestCase):
    """Không module nào ngoài `observability` import `structlog` hay tạo logger/handler riêng (06-structure.md, mục Nghĩa vụ kế thừa).
    `migrate_main` là NỢ ĐÃ KHAI BÁO: nó chạy một mình ở ngữ cảnh migrate (ADR-022), không thuộc ma trận 21 bước kiểm khởi động
    và không có trong kế hoạch B2 — xin PO quyết ở báo cáo B2 trước khi chuyển. Danh sách miễn trừ bị khoá: thêm file vào đây
    mà không sửa test là đỏ."""

    EXEMPT = {"entrypoints/migrate_main.py"}
    PATTERNS = (r"^\s*(import|from)\s+structlog\b", r"\blogging\.getLogger\(", r"\blogging\.basicConfig\(", r"\blogging\.\w*Handler\(",
                r"\.addHandler\(")

    def violations(self, only_structlog: bool = False) -> set[str]:
        found: set[str] = set()
        pats = self.PATTERNS[:1] if only_structlog else self.PATTERNS
        for f in SRC.rglob("*.py"):
            rel = f.relative_to(SRC).as_posix()
            if rel.startswith("observability/"):
                continue
            text = f.read_text(encoding="utf-8")
            if any(re.search(p, text, re.MULTILINE) for p in pats):
                found.add(rel)
        return found

    def test_ngoai_observability_khong_tao_logger_hay_handler(self):
        self.assertEqual(self.violations(), self.EXEMPT)

    def test_chi_log_py_import_structlog(self):
        in_obs = {f.relative_to(SRC).as_posix() for f in SRC.rglob("observability/*.py")
                  if re.search(self.PATTERNS[0], f.read_text(encoding="utf-8"), re.MULTILINE)}
        self.assertEqual(in_obs, {"observability/log.py"})
        self.assertEqual(self.violations(only_structlog=True), set())


if __name__ == "__main__":
    unittest.main()
