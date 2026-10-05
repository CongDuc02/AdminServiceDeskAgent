"""Test bộ chạy bước kiểm khởi động — B2. Không cần PostgreSQL (kết nối giả).

Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_startup_runner -v
"""
from __future__ import annotations

import io
import json
import logging
import re
import unittest
from pathlib import Path

import psycopg

from bo19.config.settings import load_settings
from bo19.observability.log import configure_logging
from bo19.startup import runner
from bo19.startup.connect import ConnectFailure, classify_connect_error
from bo19.startup.model import MATRIX, Context, Entry, Level, Result, Step, code
from bo19.startup.registry import REGISTRY

DOC = Path(__file__).resolve().parents[2] / "docs" / "design" / "06-structure.md"

# Danh sách KHAI BÁO các bước chưa có code ở B2 — khoá bằng test. Thêm một bước vào `registry.py` mà không sửa danh sách này là đỏ;
# sửa danh sách này mà không thêm bước vào `registry.py` cũng đỏ. Mỗi lần một bước được làm xong, bỏ nó khỏi danh sách trong cùng commit.
DECLARED_PENDING = ("3", "4a", "4b", "4c", "5", "6", "7", "8", "9", "14", "18", "21")

GOOD_ENV = {"BO19_ENVIRONMENT": "dev", "BO19_DATABASE_URL": "postgresql://u:BI_MAT@h/db", "BO19_SESSION_SECRET": "BI_MAT_SESSION_KHONG_DUOC_LOT_RA_LOG"}


class FakeConn:
    closed = False

    def __init__(self) -> None:
        self.rollbacks = 0

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


def ok_connector(_dsn: str, _app: str) -> FakeConn:
    return FakeConn()


def failing_connector(message: str):
    def connect(_dsn: str, _app: str):
        raise psycopg.OperationalError(message)
    return connect


class RunnerCase(unittest.TestCase):
    def setUp(self) -> None:
        self.out = io.StringIO()
        self.handler = configure_logging(self.out)
        self.addCleanup(logging.getLogger().removeHandler, self.handler)
        self.settings = load_settings(GOOD_ENV)

    def events(self) -> list[dict]:
        return [json.loads(x) for x in self.out.getvalue().splitlines()]

    def named(self, message: str) -> list[dict]:
        return [e for e in self.events() if e["message"] == message]

    def run_with(self, steps, registry, entry=Entry.API, connector=ok_connector, settings=None):
        return runner.run(entry, settings or self.settings, GOOD_ENV, steps=steps, registry=registry, connector=connector)


def step(n: str, entries=(Entry.API,), level=Level.BLOCK, needs_db=False) -> Step:
    return Step(n, f"bước {n}", frozenset(entries), level, needs_db)


class ChayHet(RunnerCase):
    def test_khong_dung_o_buoc_truot_dau_tien_va_gom_het_ma(self):
        steps = [step("1"), step("2"), step("3")]
        registry = {"1": lambda c: Result(("STARTUP_01_A", "STARTUP_01_B")), "2": lambda c: Result(()), "3": lambda c: Result(("STARTUP_03_C",))}
        report = self.run_with(steps, registry)
        self.assertEqual(report.failures, ("STARTUP_01_A", "STARTUP_01_B", "STARTUP_03_C"))
        self.assertEqual(report.passed, ("2",))
        self.assertFalse(report.ok)
        self.assertEqual([e["code"] for e in self.named("STARTUP_FAIL")], list(report.failures))
        self.assertEqual(self.named("STARTUP_ABORT")[0]["failed"], 3)
        self.assertEqual(self.named("STARTUP_OK"), [])

    def test_tat_ca_dat(self):
        report = self.run_with([step("1"), step("2")], {"1": lambda c: Result(()), "2": lambda c: Result(())})
        self.assertTrue(report.ok)
        self.assertEqual(self.named("STARTUP_OK")[0]["passed"], "1,2")
        self.assertEqual(self.named("STARTUP_FAIL"), [])

    def test_buoc_no_la_buoc_truot_khong_phai_buoc_dat(self):
        def boom(_c):
            raise RuntimeError("thông điệp có CCCD 001099012345")
        report = self.run_with([step("1"), step("2")], {"1": boom, "2": lambda c: Result(())})
        self.assertEqual(report.failures, ("STARTUP_01_CHECK_CRASHED:RuntimeError",))
        self.assertEqual(report.passed, ("2",))  # bước sau vẫn chạy
        self.assertNotIn("001099012345", self.out.getvalue())

    def test_canh_bao_khong_chan(self):
        report = self.run_with([step("1", level=Level.WARN), step("2")], {"1": lambda c: Result(("STARTUP_01_W",)), "2": lambda c: Result(())})
        self.assertTrue(report.ok)
        self.assertEqual(report.warnings, ("STARTUP_01_W",))
        self.assertEqual(self.named("STARTUP_WARN")[0]["code"], "STARTUP_01_W")

    def test_chi_chay_buoc_ap_cho_entrypoint(self):
        ran: list[str] = []
        registry = {"1": lambda c: ran.append("1") or Result(()), "2": lambda c: ran.append("2") or Result(())}
        self.run_with([step("1", (Entry.API,)), step("2", (Entry.WORKER, Entry.CRON))], registry, entry=Entry.WORKER)
        self.assertEqual(ran, ["2"])

    def test_buoc_nhan_context_dung_va_giao_dich_duoc_rollback_sau_moi_buoc(self):
        seen: list[Context] = []
        conns: list[FakeConn] = []

        def connector(dsn, app):
            conns.append(FakeConn())
            self.assertEqual(app, "bo19-api-startup")
            return conns[0]
        self.run_with([step("1", needs_db=True), step("2", needs_db=True)], {"1": lambda c: seen.append(c) or Result(()), "2": lambda c: Result(())},
                      connector=connector)
        self.assertEqual(len(conns), 1)  # một kết nối dùng chung
        self.assertEqual(conns[0].rollbacks, 2)
        self.assertTrue(conns[0].closed)
        self.assertIs(seen[0].conn, conns[0])

    def test_thong_tin_cua_buoc_duoc_ghi(self):
        self.run_with([step("1")], {"1": lambda c: Result((), {"mode": "NON_PRODUCTION"})})
        self.assertEqual(self.named("STARTUP_CHECK_INFO")[0]["mode"], "NON_PRODUCTION")


class MatDb(RunnerCase):
    STEPS = [step("1", needs_db=True), step("2", needs_db=True), step("3")]
    REG = {"1": lambda c: Result(()), "2": lambda c: Result(()), "3": lambda c: Result(())}

    def test_khong_noi_duoc_thi_buoc_can_db_bi_bo_qua_khong_tinh_la_dat(self):
        report = self.run_with(self.STEPS, self.REG, connector=failing_connector("password authentication failed for user x"))
        self.assertEqual(report.failures, ("STARTUP_DB_CONNECT_FAILED",))
        self.assertEqual((report.skipped, report.passed), (("1", "2"), ("3",)))  # bước không cần DB vẫn chạy
        self.assertEqual([e["step"] for e in self.named("STARTUP_CHECK_SKIPPED")], ["1", "2"])

    def test_o1_4_log_chi_co_lop_phan_loai_khong_co_thong_bao(self):
        self.run_with(self.STEPS, self.REG, connector=failing_connector('connection to server at "10.1.2.3", port 5432 failed: FATAL: password authentication failed'))
        detail = self.named("STARTUP_DB_CONNECT_DETAIL")[0]
        self.assertEqual((detail["failure_kind"], detail["error_type"]), ("AUTH", "OperationalError"))
        for leak in ("10.1.2.3", "5432", "FATAL", "password"):
            self.assertNotIn(leak, self.out.getvalue())

    def test_thieu_dsn_la_ma_cau_hinh_va_khong_co_ket_noi(self):
        called: list[int] = []
        settings = load_settings({k: v for k, v in GOOD_ENV.items() if k != "BO19_DATABASE_URL"})
        report = self.run_with(self.STEPS, self.REG, connector=lambda d, a: called.append(1) or FakeConn(), settings=settings)
        self.assertIn("STARTUP_CONFIG_DATABASE_URL_MISSING", report.failures)
        self.assertEqual(called, [])
        self.assertEqual(report.skipped, ("1", "2"))

    def test_khong_co_buoc_nao_can_db_thi_khong_nho_ket_noi(self):
        called: list[int] = []
        self.run_with([step("3")], {"3": lambda c: Result(())}, connector=lambda d, a: called.append(1) or FakeConn())
        self.assertEqual(called, [])


class PhanLoaiLoiNoi(unittest.TestCase):
    """O1-4 — đúng các chuỗi đã quan sát ở docs/reference/psycopg-connect-errors.md (psycopg 3.3.5)."""
    OBSERVED = {
        'connection failed: connection to server at "<ip>", port 5432 failed: FATAL:  password authentication failed for user "postgres"': ConnectFailure.AUTH,
        'connection failed: connection to server at "<ip>", port 5432 failed: FATAL:  password authentication failed for user "khong_co_role"': ConnectFailure.AUTH,
        'connection failed: connection to server at "<ip>", port 5999 failed: Connection refused\n\tIs the server running on that host and accepting TCP/IP connections?': ConnectFailure.NETWORK,
        "failed to resolve host 'host-khong-ton-tai.invalid': [Errno -2] Name or service not known": ConnectFailure.NETWORK,
        'connection failed: connection to server at "<ip>", port 5432 failed: FATAL:  database "khong_co_db" does not exist': ConnectFailure.OTHER,
    }

    def test_cac_thong_bao_da_quan_sat(self):
        for message, expected in self.OBSERVED.items():
            self.assertEqual(classify_connect_error(psycopg.OperationalError(message)), expected, message)

    def test_qua_han_la_network(self):
        self.assertEqual(classify_connect_error(psycopg.errors.ConnectionTimeout("connection timeout expired")), ConnectFailure.NETWORK)

    def test_thong_bao_chua_tung_thay_la_other_khong_doan(self):
        for message in ("no pg_hba.conf entry for host", "SSL required", "too many connections", "", "lỗi lạ"):
            self.assertEqual(classify_connect_error(psycopg.OperationalError(message)), ConnectFailure.OTHER, message)

    def test_khong_phai_loi_psycopg_cung_la_other(self):
        self.assertEqual(classify_connect_error(ValueError("authentication")), ConnectFailure.OTHER)


class BuocChuaLam(RunnerCase):
    """`STARTUP_CHECK_PENDING` — bước chưa làm phải hiện trong log MỖI lần khởi động, và danh sách đó bị khoá."""

    def test_danh_sach_chua_lam_bang_danh_sach_khai_bao(self):
        self.assertEqual(runner.pending_steps(), DECLARED_PENDING)

    def test_moi_buoc_trong_registry_nam_trong_ma_tran(self):
        self.assertLessEqual(set(REGISTRY), {s.number for s in MATRIX})

    def test_them_buoc_vao_registry_ma_khong_sua_danh_sach_la_do(self):
        """Mô phỏng: một bước mới có code nhưng danh sách khai báo không đổi — phải thấy lệch."""
        registry = {**REGISTRY, "3": lambda c: Result(())}
        self.assertNotEqual(runner.pending_steps(registry=registry), DECLARED_PENDING)
        self.assertEqual(set(DECLARED_PENDING) - set(runner.pending_steps(registry=registry)), {"3"})

    def test_bo_buoc_khoi_registry_ma_khong_sua_danh_sach_cung_la_do(self):
        registry = {k: v for k, v in REGISTRY.items() if k != "1"}
        self.assertNotEqual(runner.pending_steps(registry=registry), DECLARED_PENDING)

    def test_moi_lan_khoi_dong_ghi_pending_cho_tung_buoc_ap_cho_entrypoint(self):
        for entry in (Entry.API, Entry.WORKER, Entry.CRON):
            self.out.truncate(0), self.out.seek(0)
            report = runner.run(entry, self.settings, GOOD_ENV, connector=failing_connector("x"))
            expected = [s.number for s in MATRIX if s.applies(entry) and s.number in DECLARED_PENDING]
            self.assertEqual(report.pending, tuple(expected), entry)
            logged = [(e["step"], e["entry"]) for e in self.named("STARTUP_CHECK_PENDING")]
            self.assertEqual(logged, [(n, entry.value) for n in expected], entry)

    def test_ghi_pending_o_muc_canh_bao(self):
        runner.run(Entry.API, self.settings, GOOD_ENV, connector=failing_connector("x"))
        self.assertTrue(all(e["level"] == "WARNING" for e in self.named("STARTUP_CHECK_PENDING")))


class MaTranKhopTaiLieu(unittest.TestCase):
    """`MATRIX` phải khớp từng dòng của bảng trong 06-structure.md — số bước, cột api/worker/cron, mức."""

    @staticmethod
    def doc_rows() -> dict[str, tuple[frozenset[Entry], Level]]:
        text = DOC.read_text(encoding="utf-8")
        section = text[text.index("## 7. Bước kiểm khởi động"):]
        section = section[:section.index("\n---\n")] if "\n---\n" in section else section
        rows = {}
        for line in section.splitlines():
            m = re.match(r"^\| (\d+[abc]?) \|", line)
            if not m:
                continue
            cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
            if len(cells) != 7:
                raise AssertionError(f"dòng {m.group(1)} có {len(cells)} cột, không phải 7: {line[:80]}")
            entries = frozenset(e for e, cell in zip((Entry.API, Entry.WORKER, Entry.CRON), cells[2:5]) if cell == "✔")
            level_cell = cells[5].replace("*", "")
            level = Level.BLOCK if level_cell.startswith("Chặn") else Level.WARN if level_cell.startswith("Cảnh báo") else Level.LOG
            rows[m.group(1)] = (entries, level)
        return rows

    @unittest.skipUnless(DOC.exists(), "không có docs/ cạnh test (chạy ngoài repo)")
    def test_khop(self):
        doc = self.doc_rows()
        code_rows = {s.number: (s.entries, s.level) for s in MATRIX}
        self.assertEqual(list(code_rows), list(doc))  # cùng tập bước, cùng thứ tự
        for number in doc:
            self.assertEqual(code_rows[number], doc[number], f"bước #{number}")

    def test_so_buoc_la_21_voi_buoc_4_chia_ba(self):
        self.assertEqual(len(MATRIX), 23)
        self.assertEqual({re.match(r"\d+", s.number).group() for s in MATRIX}, {str(i) for i in range(1, 22)})

    def test_combined_la_hop_cac_cot_cong_buoc_18(self):
        combined = {s.number for s in MATRIX if s.applies(Entry.COMBINED)}
        union = {s.number for s in MATRIX if s.entries}
        self.assertEqual(combined, union | {"18"})
        self.assertNotIn("18", {s.number for s in MATRIX if s.applies(Entry.API) or s.applies(Entry.WORKER) or s.applies(Entry.CRON)})


class MaLoi(unittest.TestCase):
    def test_dinh_dang_ma(self):
        self.assertEqual(code("2", "SUPERUSER"), "STARTUP_02_SUPERUSER")
        self.assertEqual(code("11", "X"), "STARTUP_11_X")
        self.assertEqual(code("4b", "X"), "STARTUP_04B_X")


if __name__ == "__main__":
    unittest.main()
