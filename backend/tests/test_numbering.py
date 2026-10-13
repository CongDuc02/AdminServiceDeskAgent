"""`bo19.tool_layer.numbering` (B8a) — cấp số văn bản trên PostgreSQL thật, role `bo19_app` (ADR-011).

Điều được chứng minh, nói bằng hành vi:
- **chạy đồng thời:** N luồng, N `document` cùng sổ → `seq` đúng 1…N, **không lỗ, không trùng**, mỗi `document` đúng một dòng; nhiều luồng cùng MỘT `document` → một dòng, một số;
- **không lỗ khi thất bại:** giao dịch hỏng (mẫu cấu hình sai, token lạ, lỗi giữa chừng) thì `seq` không bị tiêu; số `VOIDED` không bao giờ tái sử dụng;
- **kỳ theo múi giờ của tổ chức**, không theo UTC; `YEARLY` sang năm reset, `NEVER` không; **hai dải không chung bộ đếm** (D-009);
- định dạng áp đúng dòng `effective_from` hiện hành; chuỗi số lưu nguyên; mẫu thiếu `{year}` ở sổ `YEARLY` làm giao dịch hỏng thay vì phát số trùng;
- chỉ tác nhân hệ thống; phải có lệnh phát hành của ĐÚNG `document`; `audit_event` không mang chuỗi số hay giá trị slot.

Định dạng số ở đây là **GIẢ, dựng trong fixture test** (PO, 2026-10-13): không có dòng `document_register_format` nào trong data migration. Mỗi lớp test có DATABASE RIÊNG đã migrate.

Cần BO19_TEST_PG_SUPERUSER_DSN. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_numbering -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import datetime as dt
import threading
import unittest
import uuid
from unittest import mock

from bo19.persistence.pool import Pool
from bo19.tool_layer import numbering
from bo19.tool_layer.kernel.permission import PermissionDenied, SystemActorRequired, employee_context, system_context
from tests import pg_support

UTC = dt.timezone.utc
REGISTER = "7c2f0e1a-5b3d-4c8e-9a41-1d6b7e90a001"  # sổ của WORK_CONFIRMATION — data migration 0002
PATTERN = "{seq}/{year}/{symbol}"  # GIẢ — chỉ để test


@unittest.skipUnless(pg_support.SUPERUSER_DSN, "cần BO19_TEST_PG_SUPERUSER_DSN")
class NumberingBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = pg_support.PgDb(pg_support.SUPERUSER_DSN)
        cls.pool = Pool(cls.db.dsn("bo19_app"), application_name="bo19-test-numbering", min_size=1, max_size=16)
        cls.pool.open()

    @classmethod
    def tearDownClass(cls):
        cls.pool.close()
        cls.db.drop()

    def setUp(self):
        with self.db.connect(autocommit=True) as c:  # siêu người dùng + replica: một test trước có thể để `document` ISSUED trỏ tới dòng sổ
            c.execute("set session_replication_role = replica")
            c.execute("delete from document_register_entry")
            c.execute("delete from document_register_counter")
            c.execute("delete from document_register_format")
            c.execute("update document_register set reset_policy = 'YEARLY' where id = %s", (REGISTER,))
        self.sys = system_context()

    # ---- fixture (siêu người dùng + replica: không cần dựng cả chuỗi template/phiên bản — khoá ngoại của `bo19_app` vẫn thật khi hàm chạy) ----------------------------

    def make_format(self, series: str = "TRIAL", pattern: str = PATTERN, symbol: str = "GIA", digits: int = 3, effective_from: dt.datetime | None = None) -> uuid.UUID:
        fid = uuid.uuid4()
        with self.db.connect("bo19_migrator", autocommit=True) as c:
            c.execute("insert into document_register_format (id, document_register_id, series, format_pattern, symbol, seq_min_digits, effective_from) values (%s, %s, %s, %s, %s, %s, %s)",
                      (fid, REGISTER, series, pattern, symbol, digits, effective_from or dt.datetime(2020, 1, 1, tzinfo=UTC)))
        return fid

    def make_document(self, *, mode: str = "NON_PRODUCTION", order: bool = True) -> tuple[uuid.UUID, uuid.UUID | None]:
        """(document, lệnh phát hành). `order=False`: chưa có người ra lệnh."""
        rid, did, decision = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        with self.db.connect(autocommit=True) as c:
            c.execute("set session_replication_role = replica")
            c.execute("insert into request (id, request_type_code, status, created_by_employee_id, beneficiary_employee_id) values (%s, 'WORK_CONFIRMATION', 'DRAFT', %s, %s)", (rid, uuid.uuid4(), uuid.uuid4()))
            c.execute("insert into document (id, request_id, template_version_id, status, operating_mode) values (%s, %s, %s, 'DRAFT', %s)", (did, rid, uuid.uuid4(), mode))
            if order:
                c.execute("insert into decision_record (id, kind, actor_employee_id, request_id, document_id, approval_step_id) values (%s, 'ISSUE_ORDERED', %s, %s, %s, %s)",
                          (decision, uuid.uuid4(), rid, did, uuid.uuid4()))
        return did, (decision if order else None)

    def assign(self, doc: tuple, at: dt.datetime | None = None, ctx=None):
        did, decision = doc
        return numbering.document_number_assign(self.pool, ctx or self.sys, document_id=did, issue_decision_id=decision, at=at)

    # ---- đọc kiểm ---------------------------------------------------------------------------------------------------------------

    def entries(self) -> list[dict]:
        with self.db.connect("bo19_migrator") as c:
            cur = c.execute("select id, series, period_key, seq, formatted_number, document_id, status, void_reason, voided_at from document_register_entry order by series, period_key, seq")
            return [dict(zip([d.name for d in cur.description], r)) for r in cur.fetchall()]

    def counters(self) -> dict[tuple[str, str], int]:
        with self.db.connect("bo19_migrator") as c:
            return {(r[0], r[1]): r[2] for r in c.execute("select series, period_key, next_seq from document_register_counter").fetchall()}

    def audit(self, action: str, document_id: uuid.UUID) -> list[dict]:
        """`audit_event` chỉ thêm, không xoá — nên luôn lọc theo `document` của test này."""
        with self.db.connect("bo19_migrator") as c:
            cur = c.execute("select actor_kind, actor_employee_id, action, severity, entity_type, entity_id, document_id, decision_record_id, payload from audit_event "
                            "where action = %s and document_id = %s order by occurred_at", (action, document_id))
            return [dict(zip([d.name for d in cur.description], r)) for r in cur.fetchall()]


class CapSo(NumberingBase):
    def test_cap_so_dau_tien_dung_dinh_dang_ky_va_dong_so(self):
        self.make_format()
        doc = self.make_document()
        at = dt.datetime(2026, 3, 5, 3, 0, tzinfo=UTC)
        out = self.assign(doc, at)
        self.assertEqual((out.seq, out.formatted_number, out.series, out.period_key, out.issued_date, out.created), (1, "001/2026/GIA", "TRIAL", "2026", dt.date(2026, 3, 5), True))
        (row,) = self.entries()
        self.assertEqual((row["seq"], row["formatted_number"], row["document_id"], row["status"], row["period_key"], row["series"]), (1, "001/2026/GIA", doc[0], "ASSIGNED", "2026", "TRIAL"))
        self.assertEqual(self.counters(), {("TRIAL", "2026"): 2})

    def test_so_tang_tuan_tu_qua_cac_document_va_chuoi_so_khong_trung(self):
        self.make_format()
        at = dt.datetime(2026, 3, 5, tzinfo=UTC)
        outs = [self.assign(self.make_document(), at) for _ in range(5)]
        self.assertEqual([o.seq for o in outs], [1, 2, 3, 4, 5])
        self.assertEqual([o.formatted_number for o in outs], [f"00{i}/2026/GIA" for i in range(1, 6)])

    def test_idempotent_theo_document_khong_lay_so_moi(self):
        self.make_format()
        doc = self.make_document()
        first = self.assign(doc)
        again = self.assign(doc)
        self.assertEqual((again.entry_id, again.seq, again.formatted_number, again.created), (first.entry_id, first.seq, first.formatted_number, False))
        self.assertEqual(again.issued_date, first.issued_date)
        self.assertEqual(len(self.entries()), 1)
        self.assertEqual(self.counters(), {("TRIAL", str(first.issued_date.year)): 2})
        self.assertEqual(len(self.audit("document.number_assign", doc[0])), 1)  # lần hai không ghi audit

    def test_audit_chi_mang_ma_so_dem_va_id(self):
        self.make_format(symbol="KY-HIEU-GIA")
        doc = self.make_document()
        out = self.assign(doc)
        (a,) = self.audit("document.number_assign", doc[0])
        self.assertEqual((a["actor_kind"], a["actor_employee_id"], a["severity"], a["entity_type"], a["document_id"], a["decision_record_id"]), ("SYSTEM", None, "INFO", "document", doc[0], doc[1]))
        self.assertEqual(a["payload"], {"entry_id": str(out.entry_id), "series": "TRIAL", "period_key": out.period_key, "seq": 1})
        self.assertNotIn("KY-HIEU-GIA", str(a["payload"]))
        self.assertNotIn(out.formatted_number, str(a["payload"]))


class DongThoi(NumberingBase):
    def test_n_luong_n_document_cung_so_khong_lo_khong_trung(self):
        self.make_format()
        docs = [self.make_document() for _ in range(16)]
        at = dt.datetime(2026, 6, 1, tzinfo=UTC)
        results, errors, barrier = [], [], threading.Barrier(16)

        def go(d):
            barrier.wait()
            try:
                results.append(self.assign(d, at))
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=go, args=(d,)) for d in docs]
        [t.start() for t in threads]
        [t.join(60) for t in threads]
        self.assertEqual(errors, [])
        self.assertEqual(sorted(r.seq for r in results), list(range(1, 17)))  # đúng 1…16 — không lỗ, không trùng
        self.assertEqual(len({r.formatted_number for r in results}), 16)
        rows = self.entries()
        self.assertEqual((len(rows), len({r["document_id"] for r in rows})), (16, 16))
        self.assertEqual(self.counters(), {("TRIAL", "2026"): 17})  # `seq` tồn tại khi và chỉ khi có dòng sổ mang nó

    def test_nhieu_luong_cung_mot_document_mot_dong_mot_so(self):
        self.make_format()
        doc = self.make_document()
        results, errors, barrier = [], [], threading.Barrier(8)

        def go():
            barrier.wait()
            try:
                results.append(self.assign(doc))
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=go) for _ in range(8)]
        [t.start() for t in threads]
        [t.join(60) for t in threads]
        self.assertEqual(errors, [])
        self.assertEqual(len({r.entry_id for r in results}), 1)
        self.assertEqual(sum(r.created for r in results), 1)
        self.assertEqual(len(self.entries()), 1)
        (counter,) = self.counters().values()
        self.assertEqual(counter, 2)  # không lần thử thừa nào tiêu số

    def test_hai_dai_cap_dong_thoi_khong_chung_bo_dem(self):
        self.make_format("TRIAL", symbol="GIA")
        self.make_format("OFFICIAL", pattern="{symbol}-{seq}", symbol="THAT", digits=2)
        trial = [self.make_document() for _ in range(5)]
        official = [self.make_document(mode="PRODUCTION") for _ in range(5)]
        results, barrier = [], threading.Barrier(10)

        def go(d):
            barrier.wait()
            results.append(self.assign(d, dt.datetime(2026, 6, 1, tzinfo=UTC)))

        threads = [threading.Thread(target=go, args=(d,)) for d in trial + official]
        [t.start() for t in threads]
        [t.join(60) for t in threads]
        self.assertEqual(sorted(r.seq for r in results if r.series == "TRIAL"), [1, 2, 3, 4, 5])
        self.assertEqual(sorted(r.seq for r in results if r.series == "OFFICIAL"), [1, 2, 3, 4, 5])
        self.assertTrue(all(r.formatted_number.startswith("THAT-") for r in results if r.series == "OFFICIAL"))
        self.assertEqual(self.counters(), {("TRIAL", "2026"): 6, ("OFFICIAL", "2026"): 6})


class KhongLoKhiThatBai(NumberingBase):
    def test_mau_thieu_year_o_so_yearly_hong_thay_vi_phat_so_trung(self):
        self.make_format(pattern="{seq}/{symbol}")
        first = self.assign(self.make_document(), dt.datetime(2026, 5, 1, tzinfo=UTC))
        self.assertEqual(first.formatted_number, "001/GIA")
        with self.assertRaises(numbering.NumberFormatCollision):
            self.assign(self.make_document(), dt.datetime(2027, 5, 1, tzinfo=UTC))  # năm 2027 seq 1 → "001/GIA" lại
        self.assertEqual(self.counters(), {("TRIAL", "2026"): 2})  # không có dòng bộ đếm 2027: giao dịch lăn hết
        self.assertEqual(len(self.entries()), 1)
        self.make_format(pattern="{seq}/{year}/{symbol}", effective_from=dt.datetime(2027, 1, 1, tzinfo=UTC))  # sửa cấu hình rồi cấp lại
        fixed = self.assign(self.make_document(), dt.datetime(2027, 5, 1, tzinfo=UTC))
        self.assertEqual((fixed.seq, fixed.formatted_number), (1, "001/2027/GIA"))  # seq 1: lần hỏng không tiêu số

    def test_token_la_hong_va_khong_tieu_so(self):
        self.make_format(pattern="{seq}-{khong_co}")
        with self.assertRaises(numbering.BadFormat):
            self.assign(self.make_document())
        self.assertEqual((self.entries(), self.counters()), ([], {}))

    def test_loi_giua_chung_lam_lan_ca_bo_dem(self):
        self.make_format()
        doc = self.make_document()
        with mock.patch("bo19.tool_layer.numbering.audit.record", side_effect=RuntimeError("giữa chừng")):
            with self.assertRaises(RuntimeError):
                self.assign(doc)
        self.assertEqual((self.entries(), self.counters()), ([], {}))  # dòng sổ và bộ đếm lăn cùng nhau
        self.assertEqual(self.assign(doc).seq, 1)  # không lỗ

    def test_void_roi_so_khong_tai_su_dung_va_document_cap_lai_co_so_moi(self):
        self.make_format()
        d1, d2 = self.make_document(), self.make_document()
        a = self.assign(d1)
        numbering.document_number_void(self.pool, self.sys, entry_id=a.entry_id, reason_code="RENDER_FAILED")
        rows = self.entries()
        self.assertEqual((rows[0]["status"], rows[0]["void_reason"]), ("VOIDED", "RENDER_FAILED"))
        self.assertIsNotNone(rows[0]["voided_at"])
        self.assertEqual(self.assign(d2).seq, 2)  # số 1 đã VOIDED không cấp lại
        again = self.assign(d1)  # document đó lấy lại số: dòng ASSIGNED mới
        self.assertEqual((again.seq, again.created), (3, True))
        self.assertEqual([r["seq"] for r in self.entries()], [1, 2, 3])
        (void_audit,) = self.audit("document.number_void", d1[0])
        self.assertEqual((void_audit["severity"], void_audit["payload"]["reason_code"]), ("WARNING", "RENDER_FAILED"))

    def test_void_chi_tu_assigned_va_khong_khi_document_da_issued(self):
        self.make_format()
        d1, d2 = self.make_document(), self.make_document()
        a, b = self.assign(d1), self.assign(d2)
        numbering.document_number_void(self.pool, self.sys, entry_id=a.entry_id, reason_code="LY_DO")
        with self.assertRaises(numbering.NotVoidable):
            numbering.document_number_void(self.pool, self.sys, entry_id=a.entry_id, reason_code="LY_DO")  # đã VOIDED
        with self.db.connect(autocommit=True) as c:  # document d2 đã ISSUED: trỏ tới dòng sổ của nó
            c.execute("set session_replication_role = replica")
            c.execute("update document set status = 'ISSUED', requires_seal = false, approved_content_hash = %s, approved_decision_id = %s, approved_render_id = %s, signer_employee_id = %s, "
                      "final_render_id = %s, issued_register_entry_id = %s, issued_date = current_date, issued_at = now() where id = %s",
                      (b"\x01" * 32, uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), b.entry_id, d2[0]))
        with self.assertRaises(numbering.NotVoidable):
            numbering.document_number_void(self.pool, self.sys, entry_id=b.entry_id, reason_code="LY_DO")
        with self.assertRaises(numbering.EntryNotFound):
            numbering.document_number_void(self.pool, self.sys, entry_id=uuid.uuid4(), reason_code="LY_DO")
        self.assertEqual([r["status"] for r in self.entries()], ["VOIDED", "ASSIGNED"])

    def test_ly_do_void_chi_la_ma(self):
        self.make_format()
        a = self.assign(self.make_document())
        for bad in ("", "co khoang trang", "chữ thường", "LY DO", "Ghi chú: giá trị slot"):
            with self.assertRaises(ValueError):
                numbering.document_number_void(self.pool, self.sys, entry_id=a.entry_id, reason_code=bad)
        self.assertEqual(self.entries()[0]["status"], "ASSIGNED")


class KyVaDinhDang(NumberingBase):
    def test_ky_theo_mui_gio_to_chuc_khong_theo_utc(self):
        self.make_format()
        before = self.assign(self.make_document(), dt.datetime(2026, 12, 31, 16, 59, tzinfo=UTC))  # 23:59 ngày 31/12 giờ Việt Nam
        after = self.assign(self.make_document(), dt.datetime(2026, 12, 31, 17, 1, tzinfo=UTC))  # 00:01 ngày 01/01/2027 giờ Việt Nam, vẫn là 31/12 theo UTC
        self.assertEqual((before.period_key, before.seq, before.issued_date), ("2026", 1, dt.date(2026, 12, 31)))
        self.assertEqual((after.period_key, after.seq, after.issued_date, after.formatted_number), ("2027", 1, dt.date(2027, 1, 1), "001/2027/GIA"))

    def test_yearly_reset_sang_nam_never_khong_reset(self):
        self.make_format()
        self.assign(self.make_document(), dt.datetime(2026, 6, 1, tzinfo=UTC))
        self.assign(self.make_document(), dt.datetime(2026, 7, 1, tzinfo=UTC))
        self.assertEqual(self.assign(self.make_document(), dt.datetime(2027, 6, 1, tzinfo=UTC)).seq, 1)
        with self.db.connect("bo19_migrator", autocommit=True) as c:  # đổi chu kỳ là tạo sổ mới; ở đây chỉ để thử nhánh NEVER — chủ bảng mới đổi được
            c.execute("delete from document_register_entry")
            c.execute("delete from document_register_counter")
            c.execute("update document_register set reset_policy = 'NEVER' where id = %s", (REGISTER,))
        outs = [self.assign(self.make_document(), dt.datetime(y, 6, 1, tzinfo=UTC)) for y in (2026, 2027, 2028)]
        self.assertEqual([(o.period_key, o.seq) for o in outs], [("ALL", 1), ("ALL", 2), ("ALL", 3)])
        self.assertEqual(self.counters(), {("TRIAL", "ALL"): 4})

    def test_ap_dung_dong_dinh_dang_hien_hanh_va_so_da_cap_khong_doi(self):
        self.make_format(pattern="{seq}/{symbol}", symbol="CU", digits=2, effective_from=dt.datetime(2026, 1, 1, tzinfo=UTC))
        self.make_format(pattern="{symbol}/{year}/{seq}", symbol="MOI", digits=4, effective_from=dt.datetime(2026, 9, 1, tzinfo=UTC))
        old = self.assign(self.make_document(), dt.datetime(2026, 8, 31, tzinfo=UTC))
        new = self.assign(self.make_document(), dt.datetime(2026, 9, 2, tzinfo=UTC))
        self.assertEqual((old.formatted_number, new.formatted_number), ("01/CU", "MOI/2026/0002"))
        self.assertEqual([r["formatted_number"] for r in self.entries()], ["01/CU", "MOI/2026/0002"])  # lưu nguyên

    def test_gia_tri_thay_vao_khong_bi_dien_giai_lai(self):
        self.assertEqual(numbering.render_number("{seq}|{symbol}", seq=7, min_digits=3, year=2026, symbol="{seq}{year}"), "007|{seq}{year}")
        self.assertEqual(numbering.render_number("{symbol}-{symbol}", seq=1, min_digits=1, year=2026, symbol="A"), "A-A")
        with self.assertRaises(numbering.BadFormat):
            numbering.render_number("{seq}{x}", seq=1, min_digits=1, year=2026, symbol="A")

    def test_khong_co_dinh_dang_cho_dai_nay(self):
        self.make_format("TRIAL")
        with self.assertRaises(numbering.NoFormat):
            self.assign(self.make_document(mode="PRODUCTION"))  # có dải TRIAL, thiếu dải OFFICIAL
        with self.assertRaises(numbering.NoFormat):
            self.assign(self.make_document(), dt.datetime(2019, 1, 1, tzinfo=UTC))  # trước `effective_from`
        self.assertEqual((self.entries(), self.counters()), ([], {}))


class DieuKien(NumberingBase):
    def test_chi_tac_nhan_he_thong(self):
        self.make_format()
        doc = self.make_document()
        eid = uuid.uuid4()
        with self.db.connect("bo19_migrator", autocommit=True) as c:
            c.execute("insert into employee (id, employee_code, full_name, department_code, department_name, job_title, contract_type, employment_start_date, is_active, source, synced_at) "
                      "values (%s, %s, 'GIẢ', 'PB', 'PB', 'CD', 'INDEFINITE', date '2020-01-01', true, 'TEST_FAKE', now())", (eid, f"T{uuid.uuid4().hex[:8]}"))
            c.execute("insert into employee_role (employee_id, role_code) values (%s, 'ADMIN_OFFICER')", (eid,))
        with self.pool.acquire() as conn:
            human = employee_context(conn, eid)
        with self.assertRaises(SystemActorRequired):
            self.assign(doc, ctx=human)
        with self.assertRaises(SystemActorRequired):
            numbering.document_number_void(self.pool, human, entry_id=uuid.uuid4(), reason_code="LY_DO")
        self.assertEqual(self.entries(), [])

    def test_phai_co_lenh_phat_hanh_cua_dung_document(self):
        self.make_format()
        d1, d2 = self.make_document(), self.make_document()
        no_order = self.make_document(order=False)
        with self.assertRaises(numbering.NoIssueOrder):
            self.assign((no_order[0], uuid.uuid4()))  # không có quyết định nào
        with self.assertRaises(numbering.NoIssueOrder):
            self.assign((d1[0], d2[1]))  # lệnh phát hành của document KHÁC
        with self.db.connect(autocommit=True) as c:  # quyết định có thật nhưng không phải ISSUE_ORDERED
            c.execute("set session_replication_role = replica")
            other = uuid.uuid4()
            c.execute("insert into decision_record (id, kind, actor_employee_id, request_id, document_id, approval_step_id) select %s, 'SIGNED', actor_employee_id, request_id, document_id, %s "
                      "from decision_record where id = %s", (other, uuid.uuid4(), d1[1]))
        with self.assertRaises(numbering.NoIssueOrder):
            self.assign((d1[0], other))
        self.assertEqual((self.entries(), self.counters()), ([], {}))

    def test_document_khong_ton_tai(self):
        self.make_format()
        with self.assertRaises(numbering.DocumentNotFound):
            self.assign((uuid.uuid4(), uuid.uuid4()))

    def test_khong_import_object_storage_hay_render(self):
        import pathlib
        src = pathlib.Path(numbering.__file__).read_text(encoding="utf-8")
        for forbidden in ("object_storage", "storage", "rendering", "soffice", "docx"):
            self.assertNotIn(f"import {forbidden}", src)
            self.assertNotIn(f"from bo19.tool_layer.{forbidden}", src)


if __name__ == "__main__":
    unittest.main()
