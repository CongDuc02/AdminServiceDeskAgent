"""`tool_layer.kernel` — ngữ cảnh, permission, audit, enqueue — trên PostgreSQL thật đã migrate (B5). Chuyển trạng thái: `test_kernel_transition.py`.

Điều được chứng minh: permission tính theo quyền hiệu lực chứ không theo tên vai trò, đọc lại mỗi lần; `audit_event` và job cùng giao dịch với thao tác (lăn thì lăn theo, ghi ngoài
giao dịch thì bị từ chối); payload chỉ mang mã và tham chiếu — văn bản tự do bị chặn; enqueue idempotent theo `dedupe_key`.

Cần BO19_TEST_PG_SUPERUSER_DSN. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_kernel -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import datetime as dt
import uuid
import unittest

import psycopg

from bo19.config import working_values as wv
from bo19.observability.trace import is_trace_id, trace_scope
from bo19.persistence.pool import Pool
from bo19.persistence.write import unit_of_work
from bo19.tool_layer.kernel import audit, enqueue as enq
from bo19.tool_layer.kernel.context import Actor, KernelError, NotInTransaction, ToolContext, require_transaction
from bo19.tool_layer.kernel.permission import ActorInactive, PermissionDenied, SystemActorRequired, employee_context, require, require_any, require_system, system_context
from tests import pg_support

TRACE = "0f1e2d3c-4b5a-4968-8777-665544332211"
RES = "VAN_BAN_TU_DO_CUA_NHAN_VIEN_KHONG_DUOC_VAO_AUDIT"


class ActorVaContext(unittest.TestCase):
    def test_nhan_vien_can_id_he_thong_khong_co_id_hay_permission(self):
        eid = uuid.uuid4()
        a = Actor.employee(eid, {"document.sign"})
        self.assertEqual((a.kind, a.employee_id, a.permissions), ("EMPLOYEE", eid, frozenset({"document.sign"})))
        s = Actor.system()
        self.assertEqual((s.kind, s.employee_id, s.permissions), ("SYSTEM", None, frozenset()))
        for bad in (lambda: Actor("EMPLOYEE"), lambda: Actor("SYSTEM", eid), lambda: Actor("SYSTEM", None, frozenset({"x"})), lambda: Actor("ROBOT")):
            with self.assertRaises(ValueError):
                bad()

    def test_bat_bien(self):
        a, ctx = Actor.employee(uuid.uuid4(), set()), None
        with self.assertRaises(Exception):
            a.kind = "SYSTEM"  # type: ignore[misc]
        ctx = ToolContext.create(a, TRACE)
        with self.assertRaises(Exception):
            ctx.trace_id = TRACE  # type: ignore[misc]

    def test_trace_id_dung_khuon_va_lay_tu_ngu_canh_trace(self):
        with self.assertRaises(ValueError):
            ToolContext(Actor.system(), "khong-phai-trace-id")
        with trace_scope(TRACE):
            self.assertEqual(ToolContext.create(Actor.system()).trace_id, TRACE)
        self.assertTrue(is_trace_id(ToolContext.create(Actor.system()).trace_id))  # ngoài ngữ cảnh: sinh mới
        self.assertEqual(ToolContext.create(Actor.system(), TRACE).trace_id, TRACE)  # tường minh thắng ngữ cảnh

    def test_loi_kernel_chi_mang_ma(self):
        e = KernelError("ten_bang")
        self.assertEqual((e.code, str(e)), ("KERNEL_ERROR", "KERNEL_ERROR:ten_bang"))


@unittest.skipUnless(pg_support.SUPERUSER_DSN, "cần BO19_TEST_PG_SUPERUSER_DSN")
class KernelDb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = pg_support.get_db()
        cls.pool = Pool(cls.db.dsn("bo19_app"), application_name="bo19-test-kernel", min_size=1, max_size=4)
        cls.pool.open()

    @classmethod
    def tearDownClass(cls):
        cls.pool.close()

    def setUp(self):
        self.ctx_sys = ToolContext.create(Actor.system(), TRACE)

    def audit_rows(self, entity_id: str) -> list[dict]:
        with self.db.connect("bo19_migrator") as c:
            cur = c.execute("select actor_kind, actor_employee_id, action, severity, entity_type, entity_id, request_id, payload, trace_id from audit_event where entity_id = %s order by occurred_at", (entity_id,))
            names = [d.name for d in cur.description]
            return [dict(zip(names, r)) for r in cur.fetchall()]


class Permission(KernelDb):
    def test_quyen_hieu_luc_la_goi_vai_tro_cong_quyen_cap_le_chua_thu_hoi(self):
        eid, _ = self.db.make_employee(roles=("EMPLOYEE",), grants=("document.sign",), revoked_grants=("document.issue",))
        with self.pool.acquire() as conn:
            ctx = employee_context(conn, eid, TRACE)
        self.assertIn("document.sign", ctx.actor.permissions)  # cấp lẻ còn hiệu lực
        self.assertNotIn("document.issue", ctx.actor.permissions)  # đã thu hồi
        with self.pool.acquire() as conn:
            role_perms = {r[0] for r in conn.execute("select permission_code from role_permission where role_code = 'EMPLOYEE'").fetchall()}
        self.assertTrue(role_perms and role_perms <= ctx.actor.permissions)  # gói của vai trò có đủ
        self.assertEqual((ctx.actor.kind, ctx.actor.employee_id, ctx.trace_id), ("EMPLOYEE", eid, TRACE))

    def test_cap_le_chua_toi_han_hieu_luc_khong_tinh(self):
        eid, _ = self.db.make_employee(roles=("EMPLOYEE",))
        with self.db.connect("bo19_migrator") as c:
            c.execute("insert into employee_permission_grant (id, employee_id, permission_code, granted_at) values (%s, %s, 'document.sign', now() + interval '1 day')", (uuid.uuid4(), eid))
        with self.pool.acquire() as conn:
            self.assertNotIn("document.sign", employee_context(conn, eid).actor.permissions)

    def test_doc_lai_moi_lan_thu_quyen_co_hieu_luc_ngay(self):
        eid, _ = self.db.make_employee(roles=("EMPLOYEE",), grants=("document.sign",))
        with self.pool.acquire() as conn:
            self.assertIn("document.sign", employee_context(conn, eid).actor.permissions)
            with self.db.connect("bo19_migrator") as c:
                c.execute("update employee_permission_grant set revoked_at = now() where employee_id = %s", (eid,))
            self.assertNotIn("document.sign", employee_context(conn, eid).actor.permissions)

    def test_nguoi_khong_hoat_dong_hay_khong_ton_tai_khong_co_ngu_canh(self):
        inactive, _ = self.db.make_employee(roles=("EMPLOYEE",), active=False)
        with self.pool.acquire() as conn:
            for eid in (inactive, uuid.uuid4()):
                with self.assertRaises(ActorInactive):
                    employee_context(conn, eid)

    def test_khong_kiem_theo_ten_vai_tro(self):
        # ADMIN_OFFICER không tự mang document.apply_seal ở đây; người chỉ có vai trò mà không có permission thì bị từ chối dù tên vai trò nghe "đủ quyền".
        eid, _ = self.db.make_employee(roles=("EMPLOYEE",))
        with self.pool.acquire() as conn:
            ctx = employee_context(conn, eid)
        with self.assertRaises(PermissionDenied) as cm:
            require(ctx, "document.issue")
        self.assertEqual(cm.exception.detail, "document.issue")
        require(ctx, next(iter(ctx.actor.permissions)))  # có permission thì qua

    def test_require_any_va_he_thong(self):
        ctx = ToolContext.create(Actor.employee(uuid.uuid4(), {"b.x"}), TRACE)
        require_any(ctx, ["a.x", "b.x"])
        with self.assertRaises(PermissionDenied):
            require_any(ctx, ["a.x", "c.x"])
        with self.assertRaises(PermissionDenied):
            require_any(ctx, [])  # any-of rỗng không bao giờ qua
        sysctx = system_context(TRACE)
        with self.assertRaises(PermissionDenied):
            require(sysctx, "b.x")  # hệ thống không có permission nào
        with self.assertRaises(PermissionDenied):
            require_any(sysctx, ["b.x"])
        require_system(sysctx)
        with self.assertRaises(SystemActorRequired):
            require_system(ctx)


class Audit(KernelDb):
    def employee_ctx(self):
        eid, _ = self.db.make_employee(roles=("EMPLOYEE",))
        with self.pool.acquire() as conn:
            return eid, employee_context(conn, eid, TRACE)

    def test_ghi_cung_giao_dich_va_dung_cot(self):
        eid, ctx = self.employee_ctx()
        key = f"e-{uuid.uuid4()}"
        with self.pool.acquire() as conn, unit_of_work(conn):
            event = audit.record(conn, ctx, action="request.open", entity_type="request", entity_id=key, payload={"slot_names": ["purpose", "recipient_org"], "n": 2, "ok": True, "x": None})
        (row,) = self.audit_rows(key)
        self.assertEqual((row["actor_kind"], row["actor_employee_id"], row["action"], row["severity"], row["entity_type"], row["trace_id"]), ("EMPLOYEE", eid, "request.open", "INFO", "request", TRACE))
        self.assertEqual(row["payload"], {"slot_names": ["purpose", "recipient_org"], "n": 2, "ok": True, "x": None})
        self.assertIsInstance(event, uuid.UUID)

    def test_tac_nhan_he_thong_khong_co_employee_id(self):
        key = f"e-{uuid.uuid4()}"
        with self.pool.acquire() as conn, unit_of_work(conn):
            audit.record(conn, self.ctx_sys, action="request.expire", entity_type="request", entity_id=key, severity="WARNING")
        (row,) = self.audit_rows(key)
        self.assertEqual((row["actor_kind"], row["actor_employee_id"], row["severity"]), ("SYSTEM", None, "WARNING"))

    def test_thao_tac_lan_thi_audit_lan_theo(self):
        key = f"e-{uuid.uuid4()}"
        with self.assertRaises(RuntimeError):
            with self.pool.acquire() as conn, unit_of_work(conn):
                audit.record(conn, self.ctx_sys, action="request.open", entity_type="request", entity_id=key)
                raise RuntimeError("thao tác hỏng sau khi đã ghi audit")
        self.assertEqual(self.audit_rows(key), [])  # không có dòng kiểm toán cho việc không xảy ra

    def test_ghi_ngoai_giao_dich_bi_tu_choi(self):
        key = f"e-{uuid.uuid4()}"
        with psycopg.connect(self.db.dsn("bo19_app"), autocommit=True) as conn:  # autocommit: mỗi câu tự commit — đúng thứ kernel cấm
            with self.assertRaises(NotInTransaction):
                audit.record(conn, self.ctx_sys, action="request.open", entity_type="request", entity_id=key)
            with self.assertRaises(NotInTransaction):
                require_transaction(conn)
        self.assertEqual(self.audit_rows(key), [])

    def test_hinh_dang_dong_sai_bi_tu_choi_khong_ghi_gi(self):
        key = f"e-{uuid.uuid4()}"
        bad = [dict(action="Request.Open"), dict(action="request"), dict(action="request.open.x"), dict(entity_type="Request"), dict(entity_type="1request"), dict(entity_id=""),
               dict(entity_id="co khoang trang"), dict(entity_id="x" * 65), dict(severity="ERROR"), dict(severity="info")]
        for over in bad:
            kw = dict(action="request.open", entity_type="request", entity_id=key) | over
            with self.pool.acquire() as conn, self.assertRaises(audit.AuditInvalid, msg=str(over)):
                with unit_of_work(conn):
                    audit.record(conn, self.ctx_sys, **kw)
        self.assertEqual(self.audit_rows(key), [])

    def test_payload_chi_ma_va_tham_chieu_van_ban_tu_do_bi_chan(self):
        ok = {"a": "WORK_CONFIRMATION", "b": str(uuid.uuid4()), "c": "2026-10-09T10:00:00+07:00", "d": -3, "e": [1, 2], "f": {"g": {"h": "x"}}, "i": uuid.uuid4(), "j": ""}
        key = f"e-{uuid.uuid4()}"
        with self.pool.acquire() as conn, unit_of_work(conn):
            audit.record(conn, self.ctx_sys, action="request.open", entity_type="request", entity_id=key, payload=ok)
        self.assertEqual(len(self.audit_rows(key)), 1)
        bad_payloads = [
            {"purpose": RES.replace("_", " ")},  # có khoảng trắng: văn bản
            {"purpose": "Nguyễn"},  # chữ có dấu
            {"p": "x" * 65},  # quá dài
            {"p": 1.5},  # float
            {"p": b"bytes"}, {"p": object()}, {"p": {"a": {"b": {"c": 1}}}},  # quá sâu: 4 tầng
            {"Bad": 1}, {"1k": 1}, {"k" * 42: 1}, {1: 1},  # khoá sai
            {"p": list(range(51))},  # quá nhiều phần tử
            {"p": ["a b"]}, {"p": {"q": "a\nb"}},
        ]
        for payload in bad_payloads:
            with self.assertRaises(audit.AuditInvalid, msg=repr(payload)[:60]) as cm:
                with self.pool.acquire() as conn, unit_of_work(conn):
                    audit.record(conn, self.ctx_sys, action="request.open", entity_type="request", entity_id=f"e-{uuid.uuid4()}", payload=payload)
            self.assertNotIn("Nguy", str(cm.exception))  # lỗi nêu loại sai, không nêu giá trị
            self.assertNotIn(RES.replace("_", " "), str(cm.exception))

    def test_payload_qua_lon_va_khong_phai_dict_bi_chan(self):
        too_big = {"a": ["x" * 64] * 50, "b": ["y" * 64] * 50}  # mỗi mục đều hợp lệ (≤ 50 phần tử, ≤ 64 ký tự) nhưng tổng ≈ 6.700 byte > 4096
        for payload in (too_big, [1, 2]):
            with self.assertRaises(audit.AuditInvalid):
                with self.pool.acquire() as conn, unit_of_work(conn):
                    audit.record(conn, self.ctx_sys, action="request.open", entity_type="request", entity_id="k", payload=payload)  # type: ignore[arg-type]

    def test_bo19_app_khong_sua_hay_xoa_duoc_audit(self):
        key = f"e-{uuid.uuid4()}"
        with self.pool.acquire() as conn, unit_of_work(conn):
            audit.record(conn, self.ctx_sys, action="request.open", entity_type="request", entity_id=key)
        with psycopg.connect(self.db.dsn("bo19_app"), autocommit=True) as conn:
            for sql in ("update audit_event set severity = 'INFO' where entity_id = %s", "delete from audit_event where entity_id = %s"):
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    conn.execute(sql, (key,))


class Enqueue(KernelDb):
    def jobs(self, **where) -> list[dict]:
        (col, value), = where.items()
        with self.db.connect("bo19_migrator") as c:
            cur = c.execute(f"select id, job_type, payload, dedupe_key, status, attempts, max_attempts, run_after, enqueued_at from job where {col} = %s order by enqueued_at", (value,))
            names = [d.name for d in cur.description]
            return [dict(zip(names, r)) for r in cur.fetchall()]

    def test_tao_job_voi_max_attempts_theo_loai_va_payload_tham_chieu(self):
        key = f"k-{uuid.uuid4()}"
        with self.pool.acquire() as conn, unit_of_work(conn):
            r = enq.enqueue(conn, job_type="procedure_ingest", payload={"version_id": str(uuid.uuid4())}, dedupe_key=key)
        self.assertTrue(r.created)
        (job,) = self.jobs(dedupe_key=key)
        self.assertEqual((job["id"], job["job_type"], job["status"], job["attempts"], job["max_attempts"]), (r.job_id, "procedure_ingest", "QUEUED", 0, 3))
        self.assertLessEqual(abs((job["run_after"] - job["enqueued_at"]).total_seconds()), 1)  # mặc định chạy ngay
        for jt, n in wv.JOB_MAX_ATTEMPTS.items():
            self.assertEqual(n, 3 if jt == "procedure_ingest" else 5, jt)  # 11-ops.md, mục Retry, backoff và job lỗi vĩnh viễn

    def test_job_va_thao_tac_cung_giao_dich_lan_thi_job_lan_theo(self):
        key = f"k-{uuid.uuid4()}"
        with self.assertRaises(RuntimeError):
            with self.pool.acquire() as conn, unit_of_work(conn):
                enq.enqueue(conn, job_type="notification_send", dedupe_key=key)
                raise RuntimeError("thao tác hỏng sau khi đã enqueue")
        self.assertEqual(self.jobs(dedupe_key=key), [])

    def test_enqueue_ngoai_giao_dich_bi_tu_choi(self):
        with psycopg.connect(self.db.dsn("bo19_app"), autocommit=True) as conn:
            with self.assertRaises(NotInTransaction):
                enq.enqueue(conn, job_type="notification_send", dedupe_key="khong-bao-gio")
        self.assertEqual(self.jobs(dedupe_key="khong-bao-gio"), [])

    def test_idempotent_theo_dedupe_key_khi_job_con_song(self):
        key = f"k-{uuid.uuid4()}"
        with self.pool.acquire() as conn, unit_of_work(conn):
            first = enq.enqueue(conn, job_type="render_document", dedupe_key=key)
        with self.pool.acquire() as conn, unit_of_work(conn):
            again = enq.enqueue(conn, job_type="render_document", dedupe_key=key)
            other_type = enq.enqueue(conn, job_type="notification_send", dedupe_key=key)  # cùng khoá, khác loại: job khác
        self.assertEqual((again.job_id, again.created), (first.job_id, False))
        self.assertTrue(other_type.created)
        self.assertEqual(len(self.jobs(dedupe_key=key)), 2)

    def test_job_da_ket_thuc_thi_enqueue_tao_job_moi(self):
        key = f"k-{uuid.uuid4()}"
        with self.pool.acquire() as conn, unit_of_work(conn):
            first = enq.enqueue(conn, job_type="render_document", dedupe_key=key)
        with self.db.connect("bo19_migrator") as c:
            c.execute("update job set status = 'RUNNING', locked_at = now(), lease_expires_at = now() + interval '1 min' where id = %s", (first.job_id,))
            c.execute("update job set status = 'SUCCEEDED', finished_at = now(), locked_at = NULL, lease_expires_at = NULL where id = %s", (first.job_id,))
        with self.pool.acquire() as conn, unit_of_work(conn):
            second = enq.enqueue(conn, job_type="render_document", dedupe_key=key)
        self.assertTrue(second.created)
        self.assertNotEqual(second.job_id, first.job_id)

    def test_khong_co_dedupe_key_thi_khong_gop(self):
        with self.pool.acquire() as conn, unit_of_work(conn):
            a = enq.enqueue(conn, job_type="notification_send")
            b = enq.enqueue(conn, job_type="notification_send")
        self.assertTrue(a.created and b.created)
        self.assertNotEqual(a.job_id, b.job_id)

    def test_run_after_duoc_ton_trong(self):
        when = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=2)
        key = f"k-{uuid.uuid4()}"
        with self.pool.acquire() as conn, unit_of_work(conn):
            enq.enqueue(conn, job_type="notification_send", dedupe_key=key, run_after=when)
        (job,) = self.jobs(dedupe_key=key)
        self.assertLess(abs((job["run_after"] - when).total_seconds()), 1)

    def test_loai_la_va_thieu_document_bi_tu_choi_truoc_khi_cham_db(self):
        with self.pool.acquire() as conn, unit_of_work(conn):
            with self.assertRaises(enq.UnknownJobType):
                enq.enqueue(conn, job_type="khong_co_loai_nay")
            for jt in ("resume_document_graph", "finalize_issue"):
                with self.assertRaises(enq.JobSubjectMissing):
                    enq.enqueue(conn, job_type=jt)

    def test_payload_chi_tham_chieu_va_dedupe_key_cung_khuon(self):
        with self.pool.acquire() as conn, unit_of_work(conn):
            for payload in ({"note": "văn bản tự do"}, {"note": "a b"}, {"n": 1.5}, [1]):
                with self.assertRaises(KernelError):
                    enq.enqueue(conn, job_type="notification_send", payload=payload)  # type: ignore[arg-type]
            with self.assertRaises(KernelError):
                enq.enqueue(conn, job_type="notification_send", dedupe_key="co khoang trang")


if __name__ == "__main__":
    unittest.main()
