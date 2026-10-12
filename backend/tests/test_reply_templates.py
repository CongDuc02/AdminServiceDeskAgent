"""Khuôn trả lời của `intake_graph` (`orchestrator/intake_graph/reply_templates.py`) và bước kiểm khởi động #23 — B6b.

Điều được chứng minh: file khuôn đang dùng hợp lệ và đúng 13 mã khuôn mà mã dùng; mọi loại sai của file (thiếu/thừa khuôn, tham số lệch, kiểu lạ, `{` lạ, quá dài, JSON hỏng) bị #23 bắt bằng một mã mang tên khuôn;
`render` fail-closed (thiếu/thừa tham số, kiểu sai, danh sách rỗng) và **không diễn giải** `{`, `}` nằm trong giá trị tham số.

Không cần PostgreSQL. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_reply_templates -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import copy
import json
import tempfile
import unittest
from pathlib import Path

from bo19.orchestrator.intake_graph import reply_templates as rt
from bo19.startup.checks_intake import step_23

RAW = json.loads(rt.DEFAULT_PATH.read_text(encoding="utf-8"))


def mutated(fn) -> dict:
    raw = copy.deepcopy(RAW)
    fn(raw["templates"])
    return raw


class FileDangDung(unittest.TestCase):
    def test_hop_le_va_dung_13_ma_khuon(self):
        self.assertEqual(rt.check(), ())
        t = rt.load()
        self.assertEqual(t.ids(), rt.REQUIRED_IDS)
        self.assertEqual(len(rt.REQUIRED_IDS), 13)

    def test_moi_khuon_lap_duoc_voi_tham_so_hop_le(self):
        t = rt.load()
        sample = {rt.TYPE_NAME: "giấy xác nhận công tác", rt.TYPE_NAMES: ["giấy xác nhận công tác", "giấy giới thiệu"], rt.SLOT_LABELS: ["mục đích", "nơi nhận"], rt.STATUS_LABEL: "Đang soạn"}
        raw = json.loads(rt.DEFAULT_PATH.read_text(encoding="utf-8"))["templates"]
        for tid, spec in raw.items():
            text = t.render(tid, {name: sample[kind] for name, kind in spec["params"].items()})
            self.assertTrue(text.strip(), tid)
            self.assertNotIn("{", text, tid)
            self.assertNotIn("}", text, tid)

    def test_kieu_tham_so_la_danh_sach_dong(self):
        self.assertEqual(set(rt.KINDS), {"TYPE_NAME", "TYPE_NAMES", "SLOT_LABELS", "STATUS_LABEL"})  # không có kiểu "chuỗi bất kỳ"

    def test_ma_khuon_cua_pending_question_deu_co_khuon(self):
        self.assertTrue(set(rt.PENDING_KIND_TEMPLATES.values()) <= rt.REQUIRED_IDS)


class Lap(unittest.TestCase):
    def setUp(self):
        self.t = rt.load()

    def test_lap_danh_sach_bang_dau_phay_va_chu_va_cuoi(self):
        self.assertIn("mục đích", self.t.render(rt.ASK_SLOT, {"type_name": "A", "slot_labels": ["mục đích"]}))
        self.assertIn("mục đích và nơi nhận", self.t.render(rt.ASK_SLOT, {"type_name": "A", "slot_labels": ["mục đích", "nơi nhận"]}))
        self.assertIn("mục đích, nơi nhận và số bản", self.t.render(rt.ASK_SLOT, {"type_name": "A", "slot_labels": ["mục đích", "nơi nhận", "số bản"]}))

    def test_thieu_thua_hoac_sai_kieu_tham_so_la_loi_ma(self):
        cases = {
            "thiếu": (rt.ASK_SLOT, {"type_name": "A"}),
            "thừa": (rt.ASK_SLOT, {"type_name": "A", "slot_labels": ["x"], "extra": "y"}),
            "khuôn không tham số mà có tham số": (rt.ERROR_BUSY, {"x": "y"}),
        }
        for label, (tid, params) in cases.items():
            with self.assertRaises(rt.ReplyTemplateError, msg=label) as cm:
                self.t.render(tid, params)
            self.assertEqual(cm.exception.code, "PARAM_MISMATCH", label)
        for label, params in {
            "scalar là list": {"type_name": ["A"], "slot_labels": ["x"]},
            "scalar rỗng": {"type_name": "  ", "slot_labels": ["x"]},
            "list là chuỗi": {"type_name": "A", "slot_labels": "mục đích"},
            "list rỗng": {"type_name": "A", "slot_labels": []},
            "phần tử không phải chuỗi": {"type_name": "A", "slot_labels": [1]},
            "phần tử rỗng": {"type_name": "A", "slot_labels": [" "]},
        }.items():
            with self.assertRaises(rt.ReplyTemplateError, msg=label) as cm:
                self.t.render(rt.ASK_SLOT, params)
            self.assertEqual(cm.exception.code, "PARAM_KIND", label)

    def test_khuon_la_la_loi(self):
        with self.assertRaises(rt.ReplyTemplateError) as cm:
            self.t.render("KHONG_CO", {})
        self.assertEqual(cm.exception.code, "TEMPLATE_UNKNOWN")

    def test_gia_tri_tham_so_chua_ngoac_khong_bi_dien_giai(self):
        out = self.t.render(rt.ASK_SLOT, {"type_name": "{slot_labels}", "slot_labels": ["{type_name}", "{0}", "%s", "{__class__}"]})
        self.assertIn("{slot_labels}", out)  # nguyên văn, không bị lắp lần hai
        self.assertIn("{type_name}", out)
        self.assertIn("{__class__}", out)

    def test_loi_khong_mang_gia_tri_tham_so(self):
        with self.assertRaises(rt.ReplyTemplateError) as cm:
            self.t.render(rt.ASK_SLOT, {"type_name": "GIA_TRI_RES_9f3a", "slot_labels": []})
        self.assertNotIn("GIA_TRI_RES_9f3a", str(cm.exception))


class FileHong(unittest.TestCase):
    def codes(self, raw) -> tuple[str, ...]:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.json"
            p.write_text(raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False), encoding="utf-8")
            return rt.check(p)

    def test_moi_loai_hong_bi_bat_bang_ma_mang_ten_khuon(self):
        cases = {
            "thiếu khuôn": (mutated(lambda t: t.pop("ASK_SLOT")), "TEMPLATE_MISSING:ASK_SLOT"),
            "thừa khuôn mồ côi": (mutated(lambda t: t.update({"KHUON_LA": {"text": "x", "params": {}}})), "TEMPLATE_UNUSED:KHUON_LA"),
            "tham số khai thừa": (mutated(lambda t: t["ERROR_BUSY"]["params"].update({"x": "TYPE_NAME"})), "PARAM_MISMATCH:ERROR_BUSY"),
            "tham số dùng mà không khai": (mutated(lambda t: t["ASK_SLOT"]["params"].pop("slot_labels")), "PARAM_MISMATCH:ASK_SLOT"),
            "kiểu lạ": (mutated(lambda t: t["ASK_SLOT"]["params"].update({"slot_labels": "CHUOI_BAT_KY"})), "PARAM_KIND_UNKNOWN:ASK_SLOT"),
            "ngoặc lạ": (mutated(lambda t: t["ERROR_BUSY"].update({"text": "Bận } rồi"})), "TEXT_BRACE:ERROR_BUSY"),
            "ngoặc mở lạ": (mutated(lambda t: t["ERROR_BUSY"].update({"text": "Bận {Hoa} rồi"})), "TEXT_BRACE:ERROR_BUSY"),
            "quá dài": (mutated(lambda t: t["ERROR_BUSY"].update({"text": "x" * (rt.MAX_TEXT_CHARS + 1)})), "TEXT_TOO_LONG:ERROR_BUSY"),
            "đúng trần thì qua": (mutated(lambda t: t["ERROR_BUSY"].update({"text": "x" * rt.MAX_TEXT_CHARS})), None),
            "rỗng": (mutated(lambda t: t["ERROR_BUSY"].update({"text": "   "})), "TEXT_EMPTY:ERROR_BUSY"),
            "sai hình dạng": (mutated(lambda t: t.update({"ERROR_BUSY": "chuỗi"})), "TEMPLATE_SHAPE:ERROR_BUSY"),
            "mã khuôn sai dạng": (mutated(lambda t: t.update({"error_busy": {"text": "x", "params": {}}})), "ID_FORMAT:error_busy"),
            "sai schema_version": ({**RAW, "schema_version": 2}, "SCHEMA_INVALID"),
            "thiếu templates": ({"schema_version": 1}, "SCHEMA_INVALID"),
            "JSON hỏng": ("{không phải json", "JSON_INVALID"),
        }
        for label, (raw, expected) in cases.items():
            got = self.codes(raw)
            if expected is None:
                self.assertEqual(got, (), label)
            else:
                self.assertIn(expected, got, label)

    def test_file_khong_doc_duoc(self):
        self.assertEqual(rt.check(Path("/khong/co/file.json")), ("FILE_UNREADABLE",))
        with self.assertRaises(rt.ReplyTemplateError) as cm:
            rt.load(Path("/khong/co/file.json"))
        self.assertEqual(cm.exception.code, "FILE_UNREADABLE")

    def test_load_nem_ma_dau_tien(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.json"
            p.write_text(json.dumps(mutated(lambda t: t.pop("ERROR_BUSY"))), encoding="utf-8")
            with self.assertRaises(rt.ReplyTemplateError) as cm:
                rt.load(p)
            self.assertEqual((cm.exception.code, cm.exception.detail), ("TEMPLATE_MISSING", "ERROR_BUSY"))


class Buoc23(unittest.TestCase):
    def test_file_dang_dung_qua_va_ma_tien_to_dung(self):
        self.assertEqual(step_23(None).codes, ())  # type: ignore[arg-type] — bước không đọc Context

    def test_file_hong_thi_bước_trượt_voi_ma_startup_23(self):
        from unittest import mock
        with mock.patch.object(rt, "check", return_value=("TEMPLATE_MISSING:ASK_SLOT",)):
            from bo19.startup import checks_intake
            self.assertEqual(checks_intake.step_23(None).codes, ("STARTUP_23_TEMPLATE_MISSING:ASK_SLOT",))  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
