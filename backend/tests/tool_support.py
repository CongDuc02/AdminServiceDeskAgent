"""Nền chung cho test tool của `intake_agent` (B6a): PostgreSQL thật đã migrate (kèm cấu hình `WORK_CONFIRMATION`), pool role `bo19_app`, ngữ cảnh nhân viên/hệ thống, và vài tiện ích dựng dữ liệu.

Không có test nào ở đây. Mọi nhân viên, tin nhắn, giá trị là dữ liệu giả của test; mỗi test tạo nhân viên và phiên riêng nên dùng chung một DB được.
"""
from __future__ import annotations

import datetime as dt
import unittest
import uuid

from bo19.persistence.pool import Pool
from bo19.tool_layer.endpoint_ops.chat import chat_message_append, chat_session_open
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.kernel.permission import employee_context, system_context
from bo19.tool_layer.tools.request_open import OpenResult, request_open
from tests import pg_support

RES = "NOI_DUNG_RES_KHONG_DUOC_LOT_RA_9f3a"


@unittest.skipUnless(pg_support.SUPERUSER_DSN, "cần BO19_TEST_PG_SUPERUSER_DSN")
class ToolBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = pg_support.get_db()
        cls.pool = Pool(cls.db.dsn("bo19_app"), application_name="bo19-test-tools", min_size=1, max_size=8)
        cls.pool.open()

    @classmethod
    def tearDownClass(cls):
        cls.pool.close()

    def setUp(self):
        self.sys = system_context()

    # --- dựng dữ liệu ------------------------------------------------------------------------------------------------------------

    def employee(self, roles: tuple[str, ...] = ("EMPLOYEE",), **kw) -> tuple[uuid.UUID, ToolContext]:
        employee_id, _ = self.db.make_employee(roles=roles, **kw)
        return employee_id, self.ctx(employee_id)

    def ctx(self, employee_id: uuid.UUID) -> ToolContext:
        with self.pool.acquire() as conn:
            return employee_context(conn, employee_id)

    def say(self, employee_id: uuid.UUID, ctx: ToolContext, text: str, session_id: uuid.UUID | None = None) -> tuple[uuid.UUID, uuid.UUID]:
        """Nhân viên nhắn một tin trong phiên của mình (mở phiên nếu chưa có). Trả (phiên, id tin)."""
        sid = session_id or chat_session_open(self.pool, ctx).chat_session_id
        mid = uuid.uuid4()
        chat_message_append(self.pool, ctx, chat_session_id=sid, message_id=mid, author="EMPLOYEE", body=text)
        return sid, mid

    def open_request(self, employee_id: uuid.UUID, ctx: ToolContext, text: str = "xin giấy xác nhận công tác") -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, OpenResult]:
        """Nhắn một tin rồi mở `request` `WORK_CONFIRMATION` cho chính mình. Trả (phiên, tin mở, request, kết quả)."""
        sid, mid = self.say(employee_id, ctx, text)
        result = request_open(self.pool, ctx, chat_session_id=sid, request_type="WORK_CONFIRMATION", beneficiary_employee_id=employee_id, opened_by_message_id=mid)
        return sid, mid, result.request_id, result

    # --- đọc kiểm (bằng chủ bảng, ngoài lối ghi của ứng dụng) --------------------------------------------------------------------

    def slot_rows(self, request_id: uuid.UUID) -> dict[str, dict]:
        with self.db.connect("bo19_migrator") as c:
            cur = c.execute("select slot_name, value, value_status, row_version, evidence_message_id, evidence_span, confirmed_at, provenance_source, provenance_synced_at, proposed_from_request_id "
                            "from request_slot where request_id = %s order by slot_name", (request_id,))
            names = [d.name for d in cur.description]
            return {r[0]: dict(zip(names, r)) for r in cur.fetchall()}

    def request_row(self, request_id: uuid.UUID) -> dict:
        with self.db.connect("bo19_migrator") as c:
            cur = c.execute("select status, row_version, closed_at, needs_info_asked_at, created_by_employee_id, beneficiary_employee_id, chat_session_id, opened_by_message_id, replaces_request_id "
                            "from request where id = %s", (request_id,))
            return dict(zip([d.name for d in cur.description], cur.fetchone()))

    def audit(self, request_id: uuid.UUID) -> list[dict]:
        with self.db.connect("bo19_migrator") as c:
            cur = c.execute("select actor_kind, actor_employee_id, action, severity, entity_type, entity_id, payload from audit_event where request_id = %s order by occurred_at, id", (request_id,))
            return [dict(zip([d.name for d in cur.description], r)) for r in cur.fetchall()]

    def set_status(self, request_id: uuid.UUID, status: str) -> None:
        extra = ", closed_at = now()" if status in ("FULFILLED", "REJECTED", "CANCELLED", "EXPIRED") else (", needs_info_asked_at = now()" if status == "NEEDS_INFO" else "")
        with self.db.connect("bo19_migrator") as c:
            c.execute(f"update request set status = %s{extra} where id = %s", (status, request_id))

    def make_expired(self, employee_id: uuid.UUID, slots: dict[str, object], *, cleared: bool = False, status: str = "EXPIRED", request_type: str = "WORK_CONFIRMATION",
                     closed_at: dt.datetime | None = None) -> uuid.UUID:
        """Một `request` đã đóng của `employee_id` cùng các slot ở trạng thái `CONFIRMED` (đã xác nhận trước khi hết hạn)."""
        from psycopg.types.json import Jsonb
        rid = uuid.uuid4()
        with self.db.connect("bo19_migrator") as c:
            c.execute("insert into request (id, request_type_code, status, created_by_employee_id, beneficiary_employee_id, closed_at, retained_values_cleared_at) values (%s, %s, %s, %s, %s, %s, %s)",
                      (rid, request_type, status, employee_id, employee_id, closed_at or dt.datetime.now(dt.timezone.utc), dt.datetime.now(dt.timezone.utc) if cleared else None))
            for name, value in slots.items():
                if value is None:
                    c.execute("insert into request_slot (request_id, request_type_code, slot_name, value, value_status, value_erased_at) values (%s, %s, %s, NULL, 'ERASED', now())", (rid, request_type, name))
                else:
                    c.execute("insert into request_slot (request_id, request_type_code, slot_name, value, value_status, confirmed_at) values (%s, %s, %s, %s, 'CONFIRMED', now())",
                              (rid, request_type, name, Jsonb(value)))
        return rid
