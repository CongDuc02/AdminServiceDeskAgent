"""AC-1.2 đầu-cuối qua HTTP (B9b2, ADR-041; phần sau cổng 1 của AC-1.1): ASGI app THẬT + `Dispatcher` thật + PostgreSQL, SeaweedFS, `soffice`, checkpointer THẬT; provider LLM là transport giả (PO, 2026-10-20: không gọi Groq).

Một văn bản đi trọn: nhân viên gửi yêu cầu (`POST /requests/{id}/actions/submit`) → worker dựng bản nháp → cán bộ duyệt nội dung (`approve-content`) → người ký ký (`sign`) → cán bộ đóng dấu (`apply-seal`)
→ cán bộ ra lệnh phát hành (`issue`, 202) → worker `finalize_issue` → `ISSUED`. Mỗi bước kiểm bằng HTTP (`GET /documents/{id}`, hàng đợi, `GET /requests/{id}`) và bằng bản `FINAL` tải về thật.

Điều được chứng minh, nói bằng hành vi:
- **AC-1.2:** đúng hai `decision_record` riêng `APPROVED` và `SEALED`, mỗi cái đúng một `audit_event`; `document_number` lấy từ `document_register` dải `TRIAL` (chuỗi số giả của fixture), không có số nào trước lệnh phát hành;
- **hàng đợi:** `issue-queue` hiện văn bản `SEALED` chưa có lệnh; ngay sau `issue` nó rời hàng đợi và `GET /documents/{id}` báo `issue_in_progress`; sau worker thì `ISSUED` với số, ngày, `final_render_id`;
- **bản `FINAL` tải về:** cán bộ (`request.read_all`) và người tạo (`request.read_own`, chỉ pdf, chỉ sau `ISSUED`) tải đúng byte; PDF in số, ngày, **họ tên + chức danh người ký**, không mã nhân viên; người tạo không tải được `.docx` hay bản nháp; người lạ `NOT_FOUND`;
- **người tạo theo dõi:** `GET /requests/{id}` có `documents` — `status`, và chỉ từ `ISSUED` mới có `document_number`, `issued_date`, `final_render_id`; `request` `FULFILLED`;
- **lệnh phát hành lặp lại** (cùng `Idempotency-Key`) trả cùng kết quả, không cấp thêm số; lệnh thứ hai khác khoá → `STATE_CONFLICT`.

Cần BO19_TEST_PG_SUPERUSER_DSN, BO19_TEST_S3_*, `soffice`. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_issue_e2e_http -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import re
import uuid

from fastapi.testclient import TestClient

from bo19.api.app import create_app
from bo19.api.auth import token
from bo19.api.auth.hasher import PasswordVerifier
from bo19.api.deps.state import AppState
from bo19.orchestrator.runner import document_id_for
from bo19.queue_worker.dispatcher import Dispatcher
from bo19.queue_worker.handlers import build_handlers
from tests import pg_support
from tests.auth_support import CSRF, SECRET
from tests.doc_support import BODY_OK, DocBase, draft_output
from tests.render_support import pdf_text
from tests.request_support import build_request

API = "/api/v1"
SIGNER_NAME, SIGNER_TITLE = "TRẦN THỊ KÝ (GIẢ)", "Phó Giám đốc (giả)"


class DauCuoiHttp(DocBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with cls.db.connect("bo19_migrator", autocommit=True) as c:
            reg = c.execute("select document_register_id from request_type where code = 'WORK_CONFIRMATION'").fetchone()[0]
            c.execute("delete from document_register_format")  # data migration 0003 đã nạp khuôn số thật (M1.2); fixture dùng khuôn GIẢ của riêng nó
            c.execute("insert into document_register_format (id, document_register_id, series, format_pattern, symbol, seq_min_digits, effective_from) "
                      "values (%s, %s, 'TRIAL', 'TRIAL-{seq}/{year}/{symbol}', 'THU-NGHIEM', 3, timestamptz '2020-01-01 00:00:00+00')", (uuid.uuid4(), reg))

    def setUp(self):
        super().setUp()
        self.verifier = PasswordVerifier(time_cost=1, memory_cost_kib=8, parallelism=1)
        self.app = create_app(AppState(pool=self.pool, session_secret=SECRET, verifier=self.verifier, storage=self.storage))
        self.client = TestClient(self.app, raise_server_exceptions=False, base_url="https://testserver", client=(pg_support.unique_ip(), 50000))
        self.dispatcher = Dispatcher(self.pool, build_handlers(document_runner=self.runner), poll_s=0.05, heartbeat_s=0.2, lease_s=60, drain_s=5)
        with self.db.connect("bo19_migrator") as c:  # DB riêng của lớp, dùng chung giữa các test: gỡ quyền cấp lẻ và số của test trước
            c.execute("delete from employee_permission_grant")
        self.officer_id, _ = self.db.make_employee(roles=("EMPLOYEE", "ADMIN_OFFICER"))
        self.signer_id, _ = self.db.make_employee(roles=("EMPLOYEE", "ADMIN_OFFICER"), grants=("document.sign",))
        with self.db.connect("bo19_migrator") as c:
            c.execute("update employee set full_name = %s, job_title = %s where id = %s", (SIGNER_NAME, SIGNER_TITLE, self.signer_id))
        self.stranger_id, _ = self.db.make_employee(roles=("EMPLOYEE",))

    # ---- HTTP ----------------------------------------------------------------------------------------------------------------

    def as_user(self, employee_id) -> dict[str, str]:
        return {"Cookie": f"bo19_session={token.issue(SECRET, employee_id)}"}

    def post(self, path: str, who, body: dict, key=None):
        return self.client.post(f"{API}{path}", json=body, headers={**CSRF, **self.as_user(who), "Idempotency-Key": str(key or uuid.uuid4())})

    def get(self, path: str, who):
        return self.client.get(f"{API}{path}", headers=self.as_user(who))

    def act(self, did, action: str, who, key=None, **extra):
        version = self.get(f"/documents/{did}", self.officer_id).json()["document"]["row_version"]
        return self.post(f"/documents/{did}/actions/{action}", who, {"expected_row_version": version, **extra}, key)

    def drain(self) -> int:
        n = 0
        while self.dispatcher.run_once():
            n += 1
            self.assertLess(n, 20)
        return n

    def doc(self, did, who=None) -> dict:
        r = self.get(f"/documents/{did}", who or self.officer_id)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    # ---- test ----------------------------------------------------------------------------------------------------------------

    def test_ac_1_2_tu_gui_yeu_cau_toi_issued_qua_http_va_tai_ban_final(self):
        self.llm.will("draft_free_content", draft_output())
        rid = build_request(self.pool, self.db, self.eid, self.ctx)
        did = document_id_for(rid)

        # 1. nhân viên gửi yêu cầu qua HTTP; worker dựng bản nháp (render_document)
        detail = self.get(f"/requests/{rid}", self.eid).json()
        self.assertEqual((detail["status"], detail["documents"]), ("DRAFT", []))
        submitted = self.post(f"/requests/{rid}/actions/submit", self.eid, {"expected_row_version": detail["row_version"]})
        self.assertEqual(submitted.status_code, 200, submitted.text)
        self.drain()
        self.assertEqual(self.doc(did)["document"]["status"], "PENDING_APPROVAL")
        queue = self.get("/review-queue?status=PENDING_APPROVAL", self.officer_id).json()
        self.assertIn(str(did), [i["document"]["id"] for i in queue["items"]])

        # 2. cổng 1: duyệt nội dung
        approved = self.act(did, "approve-content", self.officer_id)
        self.assertEqual(approved.status_code, 200, approved.text)
        approved_id = approved.json()["decision_record_id"]
        self.drain()
        body = self.doc(did)
        self.assertEqual(body["document"]["status"], "PENDING_SIGNATURE")
        self.assertEqual(body["approved_render_id"], str(self.scalar("select current_draft_render_id from document where id = %s", did)))

        # 3. người ký ký (đúng người được giao), rồi cổng 2: đóng dấu
        self.assertEqual(self.scalar("select signer_employee_id from document where id = %s", did), self.signer_id)
        self.assertEqual(self.act(did, "sign", self.officer_id).status_code, 403)  # không phải người được giao
        signed = self.act(did, "sign", self.signer_id)
        self.assertEqual(signed.status_code, 200, signed.text)
        self.drain()
        sealed = self.act(did, "apply-seal", self.officer_id, copies_count=1)
        self.assertEqual(sealed.status_code, 200, sealed.text)
        sealed_id = sealed.json()["decision_record_id"]
        self.drain()
        self.assertEqual(self.doc(did)["document"]["status"], "SEALED")

        # 4. chưa có lệnh: văn bản nằm ở hàng đợi phát hành, chưa có số
        self.assertIn(str(did), [i["document"]["id"] for i in self.get("/issue-queue", self.officer_id).json()["items"]])
        self.assertEqual(self.scalar("select count(*) from document_register_entry where document_id = %s", did), 0)
        self.assertEqual(self.doc(did)["document"]["document_number"], None)

        # 5. lệnh phát hành: 202, rời hàng đợi, issue_in_progress; lặp lại cùng khoá là cùng kết quả; khoá khác là STATE_CONFLICT
        key = uuid.uuid4()
        version = self.doc(did)["document"]["row_version"]
        first = self.post(f"/documents/{did}/actions/issue", self.officer_id, {"expected_row_version": version}, key)
        self.assertEqual(first.status_code, 202, first.text)
        again = self.post(f"/documents/{did}/actions/issue", self.officer_id, {"expected_row_version": version}, key)
        self.assertEqual((again.status_code, again.json()["decision_record_id"]), (202, first.json()["decision_record_id"]))
        other = self.post(f"/documents/{did}/actions/issue", self.officer_id, {"expected_row_version": version}, uuid.uuid4())
        self.assertEqual((other.status_code, other.json()["error_code"]), (409, "STATE_CONFLICT"))
        self.assertNotIn(str(did), [i["document"]["id"] for i in self.get("/issue-queue", self.officer_id).json()["items"]])
        mid = self.doc(did)["document"]
        self.assertEqual((mid["status"], mid["issue_in_progress"], mid["document_number"]), ("SEALED", True, None))  # đoạn 1: có lệnh, chưa có số
        owner_mid = self.get(f"/requests/{rid}", self.eid).json()["documents"]
        self.assertEqual([(d["status"], d["issue_in_progress"], d["document_number"], d["final_render_id"]) for d in owner_mid], [("SEALED", True, None, None)])
        self.assertEqual(self.scalar("select count(*) from document_register_entry where document_id = %s", did), 0)  # số chỉ cấp trong worker

        # 6. worker hoàn tất phát hành
        self.drain()
        final = self.doc(did)
        d = final["document"]
        year = self.scalar("select extract(year from (assigned_at at time zone 'Asia/Ho_Chi_Minh'))::int from document_register_entry where document_id = %s", did)
        self.assertEqual((d["status"], d["status_label"], d["issue_in_progress"], d["job_failed"], d["document_number"]), ("ISSUED", "Đã phát hành", False, False, f"TRIAL-001/{year}/THU-NGHIEM"))
        self.assertRegex(d["issued_date"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertIsNotNone(final["final_render_id"])
        self.assertEqual([(r["render_kind"], r["pin_reason"]) for r in final["renders"] if r["id"] == final["final_render_id"]], [("FINAL", "ISSUED")])
        self.assertEqual([x["kind"] for x in final["decisions"]], ["APPROVED", "SIGNED", "SEALED", "ISSUE_ORDERED"])

        # AC-1.2: hai decision_record riêng APPROVED và SEALED, mỗi cái đúng một audit_event; số từ document_register dải TRIAL
        self.assertEqual(self.scalar("select count(*) from decision_record where document_id = %s and kind in ('APPROVED', 'SEALED')", did), 2)
        for decision, action in ((approved_id, "document.approve_content"), (sealed_id, "document.apply_seal")):
            self.assertEqual(self.rows("select action from audit_event where decision_record_id = %s", uuid.UUID(decision)), [(action,)])
        self.assertEqual(self.scalar("select series from document_register_entry where document_id = %s", did), "TRIAL")
        self.assertEqual(self.scalar("select register_series from document where id = %s", did), "TRIAL")

        # 7. bản FINAL tải về thật: cán bộ và người tạo
        render_id = final["final_render_id"]
        officer_pdf = self.client.get(f"{API}/documents/{did}/renders/{render_id}/file?format=pdf", headers=self.as_user(self.officer_id))
        self.assertEqual(officer_pdf.status_code, 200, officer_pdf.text[:200])
        owner_pdf = self.client.get(f"{API}/documents/{did}/renders/{render_id}/file?format=pdf", headers=self.as_user(self.eid))
        self.assertEqual((owner_pdf.status_code, owner_pdf.content), (200, officer_pdf.content))
        text = re.sub(r"\s+", " ", pdf_text(owner_pdf.content))
        self.assertIn(d["document_number"], text)
        self.assertIn(f"{SIGNER_NAME}, {SIGNER_TITLE}", text)
        self.assertIn(BODY_OK, text)
        self.assertNotIn(self.scalar("select employee_code from employee where id = %s", self.signer_id), text)
        self.assertNotIn("cấp khi phát hành", text)
        # người tạo chỉ được bản FINAL dạng pdf; người lạ không thấy gì
        self.assertEqual(self.client.get(f"{API}/documents/{did}/renders/{render_id}/file?format=docx", headers=self.as_user(self.eid)).status_code, 403)
        draft_id = self.scalar("select id from document_render where document_id = %s and render_kind = 'DRAFT'", did)
        self.assertEqual(self.client.get(f"{API}/documents/{did}/renders/{draft_id}/file?format=pdf", headers=self.as_user(self.eid)).status_code, 403)
        self.assertEqual(self.client.get(f"{API}/documents/{did}/renders/{render_id}/file?format=pdf", headers=self.as_user(self.stranger_id)).status_code, 404)

        # 8. người tạo theo dõi: documents có số, ngày, final_render_id; request FULFILLED
        owner = self.get(f"/requests/{rid}", self.eid).json()
        self.assertEqual(owner["status"], "FULFILLED")
        (od,) = owner["documents"]
        self.assertEqual((od["id"], od["status"], od["document_number"], od["issued_date"], od["final_render_id"], od["issue_in_progress"]),
                         (str(did), "ISSUED", d["document_number"], d["issued_date"], render_id, False))
        self.assertEqual(self.get(f"/requests/{rid}", self.stranger_id).status_code, 404)
        self.assertNotIn(str(did), [i["document"]["id"] for i in self.get("/issue-queue", self.officer_id).json()["items"]])

        # 9. không gọi LLM lại ở bất kỳ bước nào sau soạn thảo
        self.assertEqual(self.llm_calls(), 1)
        self.assertTrue(all(j[0] == "SUCCEEDED" for j in self.rows("select status from job where subject_document_id = %s", did)))
