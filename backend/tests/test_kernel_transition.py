"""`tool_layer.kernel.transition` — điểm ghi duy nhất của `status` (mục Nghĩa vụ kế thừa của 06-structure.md) — B5.

Một câu `UPDATE` ghi `status`, `status_changed_at`, `row_version`, `updated_at` cùng các cột mốc mà ràng buộc DB đòi; cạnh phải có trong máy trạng thái; hai giao dịch đồng thời cùng chuyển
một hàng không cùng thành công. Cộng một phép **quét văn bản**: không câu SQL nào ngoài `transition.py` gán `status` của bốn bảng; không ai ngoài `audit.py` ghi `audit_event`.

Cần BO19_TEST_PG_SUPERUSER_DSN cho phần DB. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_kernel_transition -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import re
import tempfile
import threading
import unittest
import uuid
from pathlib import Path

import psycopg

from bo19.domain.request_machine import REQUEST_STATUSES, REQUEST_TRANSITIONS
from bo19.persistence.pool import Pool
from bo19.persistence.write import unit_of_work
from bo19.tool_layer.kernel import transition as tr
from bo19.tool_layer.kernel.context import NotInTransaction
from tests import pg_support

SRC = Path(__file__).resolve().parents[1] / "src" / "bo19"
STATUS_TABLES = ("request", "document", "approval_step", "room_booking")
# Câu `UPDATE <bảng có status> SET …` mà trong phần SET có `status =` (không phải `support_status =` hay `status_changed_at =`).
_ASSIGN = re.compile(r"UPDATE\s+(?:%s)\s+SET\s[^;]{0,600}?(?<![A-Za-z0-9_])status\s*=" % "|".join(STATUS_TABLES), re.IGNORECASE | re.DOTALL)
_AUDIT_INSERT = re.compile(r"INSERT\s+INTO\s+audit_event\b", re.IGNORECASE)


def scan(root: Path, pattern: re.Pattern, allowed: tuple[str, ...]) -> list[str]:
    hits = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if rel in allowed:
            continue
        if pattern.search(path.read_text(encoding="utf-8")):
            hits.append(rel)
    return hits


class QuetVanBan(unittest.TestCase):
    """CI quét văn bản — 06-structure.md: 'Điểm ghi duy nhất cộng quét văn bản'."""

    def test_khong_cau_sql_nao_ngoai_transition_gan_status(self):
        self.assertEqual(scan(SRC, _ASSIGN, ("tool_layer/kernel/transition.py",)), [])

    def test_bo_quet_bat_duoc_vi_pham_va_khong_bao_dong_nham(self):
        cases = {
            "violate_upper.py": 'c.execute("UPDATE request SET status = %s WHERE id = %s")',
            "violate_lower.py": "c.execute('update document set status=%s, updated_at = now() where id=%s')",
            "violate_multi.py": 'sql = """\nUPDATE approval_step\n   SET closed_at = now(),\n       status = \'DECIDED\'\n WHERE id = %s"""',
            "violate_room.py": 'c.execute("UPDATE room_booking SET row_version = row_version + 1, status = %s WHERE id = %s")',
            "ok_other_col.py": 'c.execute("UPDATE request SET expires_at = %s WHERE id = %s")',
            "ok_changed_at.py": 'c.execute("UPDATE request SET status_changed_at = now() WHERE id = %s")',
            "ok_support_status.py": 'c.execute("UPDATE request_type SET support_status = %s WHERE code = %s")',
            "ok_slot.py": 'c.execute("UPDATE request_slot SET value_status = %s WHERE request_id = %s")',
            "ok_job.py": 'c.execute("UPDATE job SET status = %s WHERE id = %s")',  # `job` không thuộc bốn bảng của kernel (thuộc `tool_layer.jobs`)
            "ok_select.py": 'c.execute("SELECT status FROM request WHERE id = %s")',
        }
        with tempfile.TemporaryDirectory() as d:
            for name, text in cases.items():
                (Path(d) / name).write_text(text, encoding="utf-8")
            self.assertEqual(scan(Path(d), _ASSIGN, ()), sorted(n for n in cases if n.startswith("violate")))

    def test_chi_audit_py_ghi_audit_event(self):
        self.assertEqual(scan(SRC, _AUDIT_INSERT, ("tool_layer/kernel/audit.py",)), [])
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "x.py").write_text('c.execute("insert into audit_event (id) values (1)")', encoding="utf-8")
            self.assertEqual(scan(Path(d), _AUDIT_INSERT, ()), ["x.py"])

    def test_transition_py_la_noi_duy_nhat_co_cau_update_dong(self):
        text = (SRC / "tool_layer" / "kernel" / "transition.py").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r'f"UPDATE \{table\} SET', text)), 1)  # đúng một câu UPDATE đổi status

    def test_bon_bang_cua_quet_khop_danh_sach_cua_kernel(self):
        self.assertEqual(tr.STATUS_TABLES, STATUS_TABLES)


class KhongCoMayThiBiTuChoi(unittest.TestCase):
    def test_chi_request_dang_ky_o_b5(self):
        self.assertEqual(set(tr.SPECS), {"request"})
        self.assertIs(tr.SPECS["request"].machine, REQUEST_TRANSITIONS)


@unittest.skipUnless(pg_support.SUPERUSER_DSN, "cần BO19_TEST_PG_SUPERUSER_DSN")
class ChuyenTrangThai(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = pg_support.get_db()
        cls.pool = Pool(cls.db.dsn("bo19_app"), application_name="bo19-test-transition", min_size=1, max_size=4)
        cls.pool.open()

    @classmethod
    def tearDownClass(cls):
        cls.pool.close()

    def go(self, request_id, **kw):
        with self.pool.acquire() as conn, unit_of_work(conn):
            return tr.transition(conn, "request", request_id, **kw)

    def test_ghi_status_va_ba_cot_cung_mot_cau(self):
        rid = self.db.make_request("DRAFT")
        before = self.db.request_row(rid)
        r = self.go(rid, to="SUBMITTED", expected_from="DRAFT", expected_row_version=before["row_version"], extra_now=("submitted_at",))
        after = self.db.request_row(rid)
        self.assertEqual((r.status, r.row_version, r.changed), ("SUBMITTED", before["row_version"] + 1, True))
        self.assertEqual((after["status"], after["row_version"]), ("SUBMITTED", before["row_version"] + 1))
        self.assertGreater(after["status_changed_at"], before["status_changed_at"])
        self.assertGreater(after["updated_at"], before["updated_at"])
        self.assertIsNotNone(after["submitted_at"])
        self.assertIsNone(after["closed_at"])

    def test_vao_needs_info_dat_moc_hoi_ma_rang_buoc_dong(self):
        rid = self.db.make_request("DRAFT")
        self.go(rid, to="NEEDS_INFO")
        self.assertIsNotNone(self.db.request_row(rid)["needs_info_asked_at"])  # ck_request_needs_info_anchor
        self.go(rid, to="DRAFT")
        self.assertEqual(self.db.request_row(rid)["status"], "DRAFT")

    def test_vao_trang_thai_cuoi_dat_closed_at(self):
        for path, final in ((("DRAFT",), "CANCELLED"), (("DRAFT", "NEEDS_INFO"), "EXPIRED"), (("DRAFT", "SUBMITTED", "IN_REVIEW"), "REJECTED"),
                            (("DRAFT", "SUBMITTED", "IN_REVIEW", "APPROVED"), "FULFILLED")):
            rid = self.db.make_request("DRAFT")
            for step in path[1:]:
                self.go(rid, to=step)
            self.go(rid, to=final)
            row = self.db.request_row(rid)
            self.assertEqual(row["status"], final)
            self.assertIsNotNone(row["closed_at"], final)  # ck_request_closed_iff_terminal

    def test_moi_canh_cua_may_di_duoc_moi_canh_ngoai_may_bi_tu_choi(self):
        for source in REQUEST_STATUSES:
            for target in REQUEST_STATUSES:
                if source == target:
                    continue
                rid = self.db.make_request(source)
                if target in REQUEST_TRANSITIONS[source]:
                    self.assertTrue(self.go(rid, to=target).changed, (source, target))
                else:
                    with self.assertRaises(tr.IllegalTransition, msg=(source, target)):
                        self.go(rid, to=target)
                    self.assertEqual(self.db.request_row(rid)["status"], source)  # không thay đổi gì

    def test_chuyen_sang_trang_thai_dang_co_la_khong_lam_gi(self):
        rid = self.db.make_request("DRAFT")
        before = self.db.request_row(rid)
        r = self.go(rid, to="DRAFT")
        self.assertEqual((r.status, r.row_version, r.changed), ("DRAFT", before["row_version"], False))
        self.assertEqual(self.db.request_row(rid), before)  # kể cả status_changed_at, updated_at

    def test_trang_thai_cuoi_khong_chuyen_di_dau_duoc(self):
        for final in ("FULFILLED", "REJECTED", "CANCELLED", "EXPIRED"):
            rid = self.db.make_request(final)
            for target in REQUEST_STATUSES:
                if target != final:
                    with self.assertRaises(tr.IllegalTransition, msg=(final, target)):
                        self.go(rid, to=target)

    def test_expected_from_va_row_version_lech_bi_tu_choi(self):
        rid = self.db.make_request("DRAFT")
        with self.assertRaises(tr.StaleStatus):
            self.go(rid, to="SUBMITTED", expected_from="NEEDS_INFO")
        with self.assertRaises(tr.StaleVersion):
            self.go(rid, to="SUBMITTED", expected_row_version=999)
        self.assertEqual(self.db.request_row(rid)["status"], "DRAFT")
        with self.assertRaises(tr.StaleVersion):
            self.go(rid, to="DRAFT", expected_row_version=999)  # kể cả khi đã ở trạng thái đích: người gọi đang nhìn bản cũ

    def test_hang_khong_ton_tai_bang_la_va_bang_chua_co_may(self):
        with self.assertRaises(tr.RowNotFound):
            self.go(uuid.uuid4(), to="SUBMITTED")
        with self.pool.acquire() as conn, unit_of_work(conn):
            for table in ("document", "approval_step", "room_booking", "request; DROP TABLE request", "job", ""):
                with self.assertRaises(tr.NoStateMachine, msg=table):
                    tr.transition(conn, table, uuid.uuid4(), to="X")

    def test_cot_moc_them_chi_trong_danh_sach_cho_phep(self):
        rid = self.db.make_request("DRAFT")
        for col in ("closed_at", "needs_info_asked_at", "expires_at", "status", "row_version", "id; DROP TABLE request"):
            with self.assertRaises(tr.ExtraColumnNotAllowed, msg=col):
                self.go(rid, to="SUBMITTED", extra_now=(col,))
        self.assertEqual(self.db.request_row(rid)["status"], "DRAFT")

    def test_ngoai_giao_dich_bi_tu_choi(self):
        rid = self.db.make_request("DRAFT")
        with psycopg.connect(self.db.dsn("bo19_app"), autocommit=True) as conn:
            with self.assertRaises(NotInTransaction):
                tr.transition(conn, "request", rid, to="SUBMITTED")
        self.assertEqual(self.db.request_row(rid)["status"], "DRAFT")

    def test_thao_tac_lan_thi_chuyen_trang_thai_lan_theo(self):
        rid = self.db.make_request("DRAFT")
        before = self.db.request_row(rid)
        with self.assertRaises(RuntimeError):
            with self.pool.acquire() as conn, unit_of_work(conn):
                tr.transition(conn, "request", rid, to="SUBMITTED")
                raise RuntimeError("hỏng sau khi chuyển")
        self.assertEqual(self.db.request_row(rid), before)

    def test_hai_giao_dich_dong_thoi_chi_mot_thang(self):
        rid = self.db.make_request("DRAFT")
        a_done, b_result = threading.Event(), {}

        def b():
            try:
                with self.pool.acquire() as conn, unit_of_work(conn):
                    b_result["r"] = tr.transition(conn, "request", rid, to="CANCELLED")
            except Exception as e:  # noqa: BLE001
                b_result["e"] = e
            b_result["after_a_committed"] = a_done.is_set()

        with self.pool.acquire() as conn_a:
            with unit_of_work(conn_a):
                tr.transition(conn_a, "request", rid, to="SUBMITTED")  # A giữ khoá hàng, chưa commit
                t = threading.Thread(target=b)
                t.start()
                t.join(0.6)
                self.assertTrue(t.is_alive(), "B phải bị chặn bởi khoá hàng của A, không chạy chen")
                a_done.set()
            t.join(10)
        self.assertTrue(b_result["after_a_committed"])
        self.assertIsInstance(b_result.get("e"), tr.IllegalTransition)  # B thấy SUBMITTED: SUBMITTED → CANCELLED không có trong máy
        self.assertEqual(self.db.request_row(rid)["status"], "SUBMITTED")


if __name__ == "__main__":
    unittest.main()
