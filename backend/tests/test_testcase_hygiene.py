"""Không lớp test nào được định nghĩa phương thức hay thuộc tính trùng tên với `unittest.TestCase` (trừ các điểm mở rộng của chính unittest).

Lý do (B9a, 2026-10-15): `LoiMangMa.fail(self, rid)` đè `unittest.TestCase.fail`; `assertEqual` trên tuple gọi `self.fail(msg)` khi so lệch, nên helper chạy lại `run_render(msg)` trong `assertRaises`
và nuốt luôn lỗi — mọi assert tuple của lớp không bao giờ đỏ, và hai ca sai kỳ vọng đã nằm im ở đó. Đột biến mới lộ ra. Test này quét mọi lớp trong `backend/tests/` (kể cả lớp nền ở file hỗ trợ) để lỗi cùng kiểu
không lặp lại. Phương thức phụ trợ phải đặt tên khác: `failed()`, `expect_failure()`…
Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_testcase_hygiene -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import importlib
import inspect
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
# Điểm mở rộng hợp lệ của unittest: móc vòng đời và hai thuộc tính cấu hình hiển thị lỗi.
ALLOWED = frozenset({"setUp", "tearDown", "setUpClass", "tearDownClass", "maxDiff", "longMessage"})
RESERVED = frozenset(name for name in dir(unittest.TestCase) if not (name.startswith("__") and name.endswith("__"))) - ALLOWED


def shadowing(cls: type) -> list[str]:
    """Tên trong thân lớp `cls` (không tính lớp cha) trùng tên của `unittest.TestCase` và không phải điểm mở rộng."""
    return sorted(set(vars(cls)) & RESERVED)


def test_classes() -> list[type]:
    found: dict[str, type] = {}
    for path in sorted(TESTS_DIR.glob("*.py")):
        if path.stem == "__init__":
            continue
        module = importlib.import_module(f"tests.{path.stem}")
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if issubclass(cls, unittest.TestCase) and cls.__module__.startswith("tests."):
                found[f"{cls.__module__}.{cls.__qualname__}"] = cls
                for base in cls.__mro__:  # lớp nền ở file hỗ trợ
                    if base is not unittest.TestCase and issubclass(base, unittest.TestCase) and base.__module__.startswith("tests."):
                        found[f"{base.__module__}.{base.__qualname__}"] = base
    return list(found.values())


class KhongDeTenUnittest(unittest.TestCase):
    def test_khong_lop_test_nao_de_ten_phuong_thuc_cua_unittest(self):
        classes = test_classes()
        self.assertGreater(len(classes), 100)  # quét thật, không quét rỗng
        bad = {f"{c.__module__}.{c.__qualname__}": shadowing(c) for c in classes if shadowing(c)}
        self.assertEqual(bad, {}, "đổi tên phương thức trùng tên unittest.TestCase (ví dụ fail → failed)")

    def test_bo_quet_bat_dung_loi_loi_mang_ma(self):
        class Xau(unittest.TestCase):
            def fail(self, rid):  # đúng lỗi của LoiMangMa
                return rid

            def assertSomething(self):  # noqa: N802 — không trùng tên có sẵn: không bị bắt
                pass

            def assertEqual(self, a, b, msg=None):  # noqa: N802
                pass

            def skipTest(self, reason):  # noqa: N802
                pass

        self.assertEqual(shadowing(Xau), ["assertEqual", "fail", "skipTest"])

    def test_diem_mo_rong_hop_le_khong_bi_bat(self):
        class Tot(unittest.TestCase):
            maxDiff = None

            @classmethod
            def setUpClass(cls):
                pass

            def setUp(self):
                pass

            def tearDown(self):
                pass

            @classmethod
            def tearDownClass(cls):
                pass

            def failed(self):
                pass

        self.assertEqual(shadowing(Tot), [])

    def test_ten_bi_cam_gom_fail_assert_skip_run_id(self):
        for name in ("fail", "assertEqual", "assertTrue", "assertRaises", "skipTest", "run", "id", "subTest", "addCleanup", "debug", "assertLogs"):
            self.assertIn(name, RESERVED, name)
        for name in ALLOWED:
            self.assertNotIn(name, RESERVED, name)


if __name__ == "__main__":
    unittest.main()
