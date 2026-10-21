"""Nhóm endpoint Văn bản (B9b1) — `GET /documents/{id}`, `GET /review-queue`, `GET /issue-queue`, `POST /documents/{id}/actions/{approve-content,sign,apply-seal,issue}` qua ASGI app thật,
PostgreSQL thật (DB RIÊNG của lớp test), role `bo19_app`. Mục Hàng đợi và văn bản, mục Thao tác cổng trên văn bản của 05-api.md; mục 3.4 của 09-security.md; ADR-040.

Điều được chứng minh, nói bằng hành vi:
- **NOT_FOUND hay PERMISSION_DENIED:** người không thấy được văn bản (`request.read_all`, hoặc `request.read_assigned` với bước giao cho mình) nhận `NOT_FOUND` — cùng thân với id không tồn tại — kể cả khi mang permission của thao tác;
  đã thấy mà thiếu permission thì `PERMISSION_DENIED` kèm tên permission; `read_assigned` theo định nghĩa B8b (`OPEN`/`DECIDED` có, `CANCELLED` không);
- **bốn thao tác cổng qua HTTP:** `DecisionResult` đúng hình dạng contract; `Idempotency-Key` = id quyết định, lặp lại trả cùng mã HTTP kèm `Idempotent-Replayed`, lệch người/đối tượng/loại là `IDEMPOTENCY_KEY_CONFLICT`
  không lộ gì; `STATE_CONFLICT` kèm `current_status`; D-006 là `SELF_APPROVAL_BLOCKED`; `sign` chỉ nhận người được giao (`PERMISSION_DENIED`, `permission = assignee`); `apply-seal` kiểm `page_count` của `EDGE_STAMP`; `issue` trả 202;
- **hàng đợi:** một trạng thái mỗi lần, chờ lâu nhất trước, keyset với cursor gắn bộ lọc; `issue-queue` loại văn bản đã có lệnh hay đang chờ tiếp quản; `status=APPROVED` hiện `job_failed` và `job_failed_code` (Sprint 1, ADR-040 mục 7);
- **model khớp `openapi.yaml`**; thân lỗi không mang giá trị.

Cần BO19_TEST_PG_SUPERUSER_DSN. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_documents_api -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import unittest
import uuid
from pathlib import Path

import yaml

from bo19.api.auth.hasher import PasswordVerifier
from bo19.api.schemas import documents as schemas
from bo19.persistence.pool import Pool
from bo19.tool_layer.kernel.permission import system_context
from tests import pg_support
from tests.auth_support import CSRF, AuthBase
from tests.doc_support import BODY_OK
from tests.gate_support import FlowMixin, document_row, make_officer, make_template_version, rows, scalar
from tests.tool_support import RES

API = "/api/v1"
OPENAPI = Path(__file__).resolve().parents[2] / "docs" / "design" / "contracts" / "openapi.yaml"


@unittest.skipUnless(pg_support.SUPERUSER_DSN, "cần BO19_TEST_PG_SUPERUSER_DSN")
class DocApiBase(FlowMixin, AuthBase):
    @classmethod
    def setUpClass(cls):
        cls.db = pg_support.PgDb(pg_support.SUPERUSER_DSN)
        cls.verifier = PasswordVerifier(time_cost=1, memory_cost_kib=8, parallelism=1)
        cls.pool = Pool(cls.db.dsn("bo19_app"), application_name="bo19-test-docs-api", min_size=1, max_size=5)
        cls.pool.open()
        cls.version_id = make_template_version(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.pool.close()
        cls.db.drop()

    def setUp(self):
        super().setUp()
        self.sys = system_context()
        self.officer_id, self.octx = make_officer(self.db, self.pool)
        self.h = self.as_user(self.officer_id)

    # ---- gọi -----------------------------------------------------------------------------------------------------------------

    def get_doc(self, doc, headers=None):
        return self.client.get(f"{API}/documents/{doc.document_id if hasattr(doc, 'document_id') else doc}", headers=headers or self.h)

    def queue(self, status, headers=None, **params):
        q = "&".join([f"status={status}", *[f"{k}={v}" for k, v in params.items()]]) if status else "&".join(f"{k}={v}" for k, v in params.items())
        return self.client.get(f"{API}/review-queue?{q}", headers=headers or self.h)

    def issue_queue(self, headers=None, **params):
        q = "&".join(f"{k}={v}" for k, v in params.items())
        return self.client.get(f"{API}/issue-queue" + (f"?{q}" if q else ""), headers=headers or self.h)

    def act(self, doc, action, body=None, key=None, headers=None, csrf=True, **extra):
        hdr = {**(CSRF if csrf else {}), **(headers or self.h)}
        if key is not False:
            hdr["Idempotency-Key"] = str(key or uuid.uuid4())
        payload = body if body is not None else {"expected_row_version": document_row(self.db, doc.document_id)["row_version"], **extra}
        return self.client.post(f"{API}/documents/{doc.document_id}/actions/{action}", json=payload, headers=hdr)

    def ids(self, response) -> list[str]:
        self.assertEqual(response.status_code, 200, response.text)
        return [i["document"]["id"] for i in response.json()["items"]]

    def assign_signature(self, doc, signer_id):
        """Giao bước ký cho `signer_id` bằng chủ bảng — để điều khiển người ký chính xác trên DB có nhiều người mang `document.sign` (`signing_route` chọn mã nhỏ nhất)."""
        with self.db.connect("bo19_migrator") as c:
            c.execute("update document set status = 'PENDING_SIGNATURE', signer_employee_id = %s where id = %s", (signer_id, doc.document_id))
            c.execute("insert into approval_step (id, document_id, step_kind, assignee_employee_id) values (%s, %s, 'SIGNATURE', %s)", (uuid.uuid4(), doc.document_id, signer_id))

    def signer_role(self):
        """Người dùng vai trò `SIGNER`: `request.read_assigned` + `document.sign`, không `request.read_all`."""
        eid, _ = self.db.make_employee(roles=("SIGNER",))
        return eid, self.as_user(eid)


class ChiTietVanBan(DocApiBase):
    def test_man_hinh_duyet_day_du_cac_phan(self):
        doc = self.doc()
        r = self.get_doc(doc)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        d = body["document"]
        self.assertEqual((d["id"], d["request_id"], d["status"], d["status_label"], d["operating_mode"], d["requires_seal"], d["seal_type"]),
                         (str(doc.document_id), str(doc.request_id), "PENDING_APPROVAL", "Chờ duyệt nội dung", "NON_PRODUCTION", True, "ORGANIZATION_ROUND"))
        self.assertEqual((d["issue_in_progress"], d["halted"], d["job_failed"], d["job_failed_code"], d["document_number"], d["issued_date"]), (False, False, False, None, None, None))
        self.assertEqual((body["request"]["id"], body["request"]["status"]), (str(doc.request_id), "IN_REVIEW"))
        self.assertEqual((body["template"]["template_version_id"], body["template"]["version_no"]), (str(self.version_id), 1))
        v = {x["variable_name"]: x for x in body["variables"]}
        self.assertEqual(set(v), {"full_name", "department_name", "job_title", "recipient_org", "purpose_statement", "document_number", "issued_date", "signer_user_id"})
        self.assertEqual((v["full_name"]["kind"], v["full_name"]["slot_source"], v["full_name"]["sensitivity"], v["full_name"]["provenance"]["source"]), ("DIRECT_SLOT", "HR_PROFILE", "PER", "TEST_FAKE"))
        self.assertTrue(v["full_name"]["value"].startswith("NGƯỜI GIẢ"))
        self.assertEqual((v["purpose_statement"]["kind"], v["purpose_statement"]["value"], v["purpose_statement"]["slot_source"], v["purpose_statement"]["sensitivity"]), ("FREE_CONTENT", BODY_OK, None, None))
        self.assertEqual((v["document_number"]["kind"], v["document_number"]["value"], v["document_number"]["fill_after_approval"]), ("SYSTEM", None, True))  # điền sau duyệt: chưa có giá trị
        self.assertEqual((v["recipient_org"]["kind"], v["recipient_org"]["slot_source"], v["recipient_org"]["sensitivity"], v["recipient_org"]["provenance"]), ("DIRECT_SLOT", "USER_INPUT", "PER", None))
        self.assertEqual([(x["render_kind"], x["pin_reason"]) for x in body["renders"]], [("DRAFT", None)])
        self.assertEqual((body["current_draft_render_id"], body["approved_render_id"], body["final_render_id"]), (str(doc.render_id), None, None))
        self.assertEqual([(s["step_kind"], s["status"], s["assignee_employee_id"], s["self_approved"]) for s in body["approval_steps"]], [("CONTENT_REVIEW", "OPEN", None, False)])
        self.assertEqual(body["decisions"], [])
        self.assertIsNone(body["latest_halt"])

    def test_sau_khi_duyet_ban_nhap_duoc_ghim_va_co_quyet_dinh(self):
        doc = self.doc()
        key = uuid.uuid4()
        self.approve(doc, self.octx, key)
        body = self.get_doc(doc).json()
        self.assertEqual([(x["render_kind"], x["pin_reason"]) for x in body["renders"]], [("DRAFT", "APPROVED_CONTENT")])
        self.assertEqual(body["approved_render_id"], str(doc.render_id))
        self.assertEqual(body["document"]["status"], "APPROVED")
        (dec,) = body["decisions"]
        self.assertEqual((dec["id"], dec["kind"], dec["actor"]["id"], dec["change_scope"], dec["texts"]), (str(key), "APPROVED", str(self.officer_id), None, []))
        self.assertEqual([(s["step_kind"], s["status"]) for s in body["approval_steps"]], [("CONTENT_REVIEW", "DECIDED")])

    def test_khong_thay_duoc_la_not_found_cung_than_voi_id_khong_ton_tai(self):
        doc = self.doc()
        creator = self.as_user(doc.beneficiary_id)  # người tạo yêu cầu: chỉ request.read_own, không gọi GET /documents/{id}
        plain, _ = self.db.make_employee(roles=("EMPLOYEE",))
        a = self.assert_envelope(self.get_doc(doc, creator), "NOT_FOUND", 404)
        b = self.assert_envelope(self.get_doc(uuid.uuid4(), creator), "NOT_FOUND", 404)
        c = self.assert_envelope(self.get_doc(doc, self.as_user(plain)), "NOT_FOUND", 404)
        self.assertEqual({k: v for k, v in a.items() if k != "trace_id"}, {k: v for k, v in b.items() if k != "trace_id"})
        self.assertEqual({k: v for k, v in c.items() if k != "trace_id"}, {k: v for k, v in b.items() if k != "trace_id"})

    def test_read_assigned_chi_thay_van_ban_co_buoc_giao_cho_minh(self):
        signer, h = self.signer_role()
        mine, other = self.doc(), self.doc()
        for d in (mine, other):
            self.approve(d, self.octx)
        self.assertEqual(self.get_doc(mine, h).status_code, 404, "chưa được giao bước nào thì chưa thấy")
        self.assign_signature(mine, signer)
        r = self.get_doc(mine, h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["document"]["status"], "PENDING_SIGNATURE")
        self.assert_envelope(self.get_doc(other, h), "NOT_FOUND", 404)  # văn bản khác: không thấy

    def test_read_assigned_buoc_decided_van_thay_con_cancelled_thi_khong(self):
        signer, h = self.signer_role()
        doc = self.doc()
        self.approve(doc, self.octx)
        self.assign_signature(doc, signer)
        with self.db.connect("bo19_migrator") as c:
            c.execute("update approval_step set status = 'DECIDED', closed_at = now() where document_id = %s and step_kind = 'SIGNATURE'", (doc.document_id,))
        self.assertEqual(self.get_doc(doc, h).status_code, 200)  # người đã quyết xong vẫn xem được văn bản mình duyệt (B8b)
        with self.db.connect("bo19_migrator") as c:
            c.execute("update approval_step set status = 'CANCELLED' where document_id = %s and step_kind = 'SIGNATURE'", (doc.document_id,))
        self.assert_envelope(self.get_doc(doc, h), "NOT_FOUND", 404)

    def test_chua_dang_nhap_va_id_hong(self):
        self.assert_envelope(self.client.get(f"{API}/documents/{uuid.uuid4()}"), "UNAUTHENTICATED", 401)
        self.assert_envelope(self.client.get(f"{API}/documents/khong-phai-uuid", headers=self.h), "VALIDATION_FAILED", 422)

    def test_phan_hoi_phan_anh_khoang_hoan_tat_phat_hanh(self):
        doc, _, _ = self.sealed()
        self.issue(doc, self.octx)
        d = self.get_doc(doc).json()["document"]
        self.assertEqual((d["status"], d["issue_in_progress"], d["status_label"], d["document_number"]), ("SEALED", True, "Đang cấp số và phát hành", None))  # status vẫn là mã thật; chưa có số


class HangDoiDuyet(DocApiBase):
    def test_mot_trang_thai_moi_lan_va_chi_dung_trang_thai_do(self):
        a, b = self.doc(), self.doc()
        self.approve(b, self.octx)
        pending = self.ids(self.queue("PENDING_APPROVAL"))
        self.assertIn(str(a.document_id), pending)
        self.assertNotIn(str(b.document_id), pending)  # đã APPROVED
        item = next(i for i in self.queue("PENDING_APPROVAL").json()["items"] if i["document"]["id"] == str(a.document_id))
        self.assertEqual(set(item), {"document", "request_type_name", "beneficiary"})
        self.assertEqual((item["beneficiary"]["id"], item["request_type_name"]), (str(a.beneficiary_id), "Giấy xác nhận công tác"))

    def test_cho_lau_nhat_truoc_va_phan_trang_keyset(self):
        first, second, third = self.doc(), self.doc(), self.doc()
        want = [str(d.document_id) for d in (first, second, third)]
        seen: list[str] = []
        times: list[str] = []
        cursor = None
        pages = 0
        while True:
            r = self.queue("PENDING_APPROVAL", limit=1, **({"cursor": cursor} if cursor else {}))
            self.assertEqual(r.status_code, 200, r.text)
            body = r.json()
            self.assertLessEqual(len(body["items"]), 1)
            seen += [i["document"]["id"] for i in body["items"]]
            times += [i["document"]["status_changed_at"] for i in body["items"]]
            pages += 1
            cursor = body["next_cursor"]
            if cursor is None:
                break
            self.assertLess(pages, 200)
        self.assertEqual(len(seen), len(set(seen)))  # không trùng giữa các trang
        self.assertEqual([i for i in seen if i in want], want)  # đúng thứ tự tạo = chờ lâu nhất trước
        self.assertEqual(times, sorted(times))  # tăng dần xuyên các trang

    def test_cursor_gan_bo_loc(self):
        self.doc()
        self.doc()
        cursor = self.queue("PENDING_APPROVAL", limit=1).json()["next_cursor"]
        self.assertIsNotNone(cursor)
        body = self.assert_envelope(self.queue("PENDING_SEAL", cursor=cursor), "VALIDATION_FAILED", 422)
        self.assertEqual(body["details"]["fields"], [{"field": "cursor", "code": "INVALID_FORMAT"}])
        self.assert_envelope(self.queue("PENDING_APPROVAL", cursor="khong-phai-cursor"), "VALIDATION_FAILED", 422)

    def test_status_bat_buoc_mot_gia_tri_hop_le(self):
        self.assert_envelope(self.queue(None), "VALIDATION_FAILED", 422)
        self.assert_envelope(self.queue("ISSUED"), "VALIDATION_FAILED", 422)
        self.assert_envelope(self.queue("DRAFT"), "VALIDATION_FAILED", 422)

    def test_permission_theo_status(self):
        doc, signer, _ = self.pending_seal()
        expect = {"PENDING_APPROVAL": "document.approve_content", "APPROVED": "document.approve_content", "PENDING_SIGNATURE": "document.sign", "PENDING_SEAL": "document.apply_seal"}
        for status, permission in expect.items():
            r = self.queue(status, self.as_user(self.db.make_employee(roles=("EMPLOYEE",))[0]))
            body = self.assert_envelope(r, "PERMISSION_DENIED", 403)
            self.assertEqual(body["details"], {"permission": permission}, status)
        self.assertEqual(self.queue("PENDING_SEAL").status_code, 200)  # ADMIN_OFFICER mang apply_seal
        body = self.assert_envelope(self.queue("PENDING_SIGNATURE"), "PERMISSION_DENIED", 403)  # nhưng không mang document.sign (cấp lẻ)
        self.assertEqual(body["details"], {"permission": "document.sign"})
        self.assertIn(str(doc.document_id), self.ids(self.queue("PENDING_SEAL")))

    def test_co_permission_cong_nhung_thieu_ca_hai_quyen_xem_la_forbidden(self):
        eid, _ = self.db.make_employee(roles=("EMPLOYEE",), grants=("document.approve_content",))
        self.assert_envelope(self.queue("PENDING_APPROVAL", self.as_user(eid)), "PERMISSION_DENIED", 403)

    def test_read_assigned_chi_thay_hang_doi_cua_minh(self):
        signer, h = self.signer_role()
        mine, other = self.doc(), self.doc()
        for d in (mine, other):
            self.approve(d, self.octx)
        self.assign_signature(mine, signer)
        self.assign_signature(other, self.db.make_employee(roles=("SIGNER",))[0])  # cũng chờ ký, nhưng giao cho người khác
        self.assertEqual(self.ids(self.queue("PENDING_SIGNATURE", h)), [str(mine.document_id)])  # chỉ văn bản có bước giao cho mình
        with self.db.connect("bo19_migrator") as c:
            c.execute("update approval_step set status = 'CANCELLED', closed_at = now() where document_id = %s and step_kind = 'SIGNATURE'", (mine.document_id,))
        self.assertEqual(self.ids(self.queue("PENDING_SIGNATURE", h)), [])  # bước CANCELLED không còn là việc được giao

    def test_hang_doi_approved_hien_job_failed_va_ma_cua_sprint_1(self):
        doc = self.doc()
        self.approve(doc, self.octx)  # job resume QUEUED, document ở APPROVED
        item = lambda: next(i for i in self.queue("APPROVED").json()["items"] if i["document"]["id"] == str(doc.document_id))["document"]  # noqa: E731
        self.assertEqual((item()["status"], item()["job_failed"], item()["job_failed_code"]), ("APPROVED", False, None))
        with self.db.connect("bo19_migrator") as c:
            c.execute("update job set status = 'FAILED', attempts = 1, started_at = now(), finished_at = now(), last_error_code = 'NO_ELIGIBLE_SIGNER' where subject_document_id = %s", (doc.document_id,))
        self.assertEqual((item()["job_failed"], item()["job_failed_code"], item()["status_label"]), (True, "NO_ELIGIBLE_SIGNER", "Đã duyệt nội dung, chờ ký"))
        with self.db.connect("bo19_migrator") as c:  # job mới hơn thành công: cờ tắt (chỉ job MỚI NHẤT tính)
            c.execute("insert into job (id, job_type, payload, subject_document_id, status, attempts, max_attempts, started_at, finished_at, enqueued_at) "
                      "values (%s, 'resume_document_graph', '{}', %s, 'SUCCEEDED', 1, 5, now(), now(), now() + interval '1 second')", (uuid.uuid4(), doc.document_id))
        self.assertEqual((item()["job_failed"], item()["job_failed_code"]), (False, None))


class HangDoiPhatHanh(DocApiBase):
    def test_sealed_va_signed_khong_can_dau_co_mat_pending_seal_thi_khong(self):
        sealed, _, _ = self.sealed()
        noseal, (_, sctx), _ = self.pending_signature(requires_seal=False)
        self.sign(noseal, sctx)
        pending_seal, _, _ = self.pending_seal()
        ids = self.ids(self.issue_queue())
        self.assertIn(str(sealed.document_id), ids)
        self.assertIn(str(noseal.document_id), ids)
        self.assertNotIn(str(pending_seal.document_id), ids)

    def test_da_co_lenh_phat_hanh_thi_roi_khoi_hang_doi(self):
        doc, _, _ = self.sealed()
        self.assertIn(str(doc.document_id), self.ids(self.issue_queue()))
        self.issue(doc, self.octx)
        self.assertNotIn(str(doc.document_id), self.ids(self.issue_queue()))

    def test_dang_cho_tiep_quan_thi_khong_nam_trong_hang_doi(self):
        doc, _, _ = self.sealed()
        with self.db.connect("bo19_migrator") as c:
            c.execute("insert into approval_step (id, document_id, step_kind, status) values (%s, %s, 'TAKEOVER', 'OPEN')", (uuid.uuid4(), doc.document_id))
        self.assertNotIn(str(doc.document_id), self.ids(self.issue_queue()))
        self.assertTrue(self.get_doc(doc).json()["document"]["halted"])

    def test_phan_trang_va_thu_tu(self):
        docs = [self.sealed()[0] for _ in range(3)]
        want = [str(d.document_id) for d in docs]
        seen, cursor = [], None
        for _ in range(200):
            body = self.issue_queue(limit=1, **({"cursor": cursor} if cursor else {})).json()
            seen += [i["document"]["id"] for i in body["items"]]
            cursor = body["next_cursor"]
            if cursor is None:
                break
        self.assertEqual([i for i in seen if i in want], want)

    def test_can_document_issue(self):
        plain, _ = self.db.make_employee(roles=("EMPLOYEE",))
        body = self.assert_envelope(self.issue_queue(self.as_user(plain)), "PERMISSION_DENIED", 403)
        self.assertEqual(body["details"], {"permission": "document.issue"})
        self.assert_envelope(self.client.get(f"{API}/issue-queue"), "UNAUTHENTICATED", 401)


class ThaoTacCong(DocApiBase):
    def test_duyet_noi_dung_200_dung_hinh_dang(self):
        doc = self.doc()
        key = uuid.uuid4()
        r = self.act(doc, "approve-content", key=key)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn("idempotent-replayed", r.headers)
        body = r.json()
        self.assertEqual((body["decision_record_id"], body["kind"]), (str(key), "APPROVED"))
        self.assertEqual((body["document"]["status"], body["document"]["id"], body["document"]["row_version"]), ("APPROVED", str(doc.document_id), document_row(self.db, doc.document_id)["row_version"]))
        self.assertEqual((body["request"]["id"], body["request"]["status"]), (str(doc.request_id), "IN_REVIEW"))  # approve-content không đổi request
        self.assertEqual(rows(self.db, "select kind from decision_record where id = %s", key), [("APPROVED",)])

    def test_lap_lai_cung_khoa_cung_ma_http_kem_co_replayed(self):
        doc = self.doc()
        key = uuid.uuid4()
        first = self.act(doc, "approve-content", key=key)
        again = self.act(doc, "approve-content", key=key, body={"expected_row_version": 1})
        self.assertEqual((first.status_code, again.status_code, again.headers.get("idempotent-replayed")), (200, 200, "true"))
        self.assertEqual(first.json()["decision_record_id"], again.json()["decision_record_id"])
        self.assertEqual(scalar(self.db, "select count(*) from decision_record where document_id = %s", doc.document_id), 1)

    def test_trung_khoa_lech_nguoi_doi_tuong_loai_khong_lo_noi_dung(self):
        doc, other = self.doc(), self.doc()
        key = uuid.uuid4()
        self.assertEqual(self.act(doc, "approve-content", key=key).status_code, 200)
        _, octx2 = make_officer(self.db, self.pool)
        for response in (self.act(doc, "approve-content", key=key, headers=self.as_user(octx2.actor.employee_id)),  # khác người
                         self.act(other, "approve-content", key=key)):  # khác đối tượng
            body = self.assert_envelope(response, "IDEMPOTENCY_KEY_CONFLICT", 409)
            self.assertNotIn(str(doc.document_id), response.text)
            self.assertNotIn("APPROVED", response.text)
            self.assertNotIn("details", body)

    def test_thieu_khoa_khoa_hong_thieu_csrf_va_truong_la(self):
        doc = self.doc()
        self.assert_envelope(self.act(doc, "approve-content", key=False), "IDEMPOTENCY_KEY_REQUIRED", 400)
        r = self.client.post(f"{API}/documents/{doc.document_id}/actions/approve-content", json={"expected_row_version": 1}, headers={**CSRF, **self.h, "Idempotency-Key": "khong-phai-uuid"})
        body = self.assert_envelope(r, "VALIDATION_FAILED", 422)
        self.assertEqual(body["details"]["fields"], [{"field": "Idempotency-Key", "code": "INVALID_FORMAT"}])
        self.assert_envelope(self.act(doc, "approve-content", csrf=False), "CSRF_HEADER_MISSING", 403)
        body = self.assert_envelope(self.act(doc, "approve-content", body={"expected_row_version": 1, "submit_ready": True}), "VALIDATION_FAILED", 422)
        self.assertEqual(body["details"]["fields"], [{"field": "submit_ready", "code": "NOT_ALLOWED"}])
        self.assert_envelope(self.act(doc, "approve-content", body={}), "VALIDATION_FAILED", 422)
        self.assertEqual(document_row(self.db, doc.document_id)["status"], "PENDING_APPROVAL")  # không lần nào ghi gì

    def test_self_approval_reason_duoc_nhan_va_bo_qua(self):
        doc = self.doc()
        r = self.act(doc, "approve-content", self_approval_reason="lý do không cần thiết")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(scalar(self.db, "select count(*) from approval_step where document_id = %s and self_approved", doc.document_id), 0)  # không lưu khi không bị chặn
        self.assert_envelope(self.act(self.doc(), "approve-content", self_approval_reason=""), "VALIDATION_FAILED", 422)

    def test_state_conflict_kem_current_status(self):
        doc = self.doc()
        self.act(doc, "approve-content")
        body = self.assert_envelope(self.act(doc, "approve-content"), "STATE_CONFLICT", 409)
        self.assertEqual(body["details"], {"current_status": "APPROVED"})
        stale = self.assert_envelope(self.act(self.doc(), "approve-content", body={"expected_row_version": 99}), "STATE_CONFLICT", 409)
        self.assertEqual(stale["details"], {"current_status": "PENDING_APPROVAL"})

    def test_thieu_permission_nhung_thay_duoc_la_403_khong_thay_la_404(self):
        signer, h = self.signer_role()
        doc = self.doc()
        self.approve(doc, self.octx)
        self.assign_signature(doc, signer)
        # người ký (read_assigned, thấy văn bản) gọi thao tác không phải của mình: 403 kèm tên permission
        body = self.assert_envelope(self.act(doc, "apply-seal", headers=h, copies_count=1), "PERMISSION_DENIED", 403)
        self.assertEqual(body["details"], {"permission": "document.apply_seal"})
        # cán bộ thường (read_all) gọi `sign`: thấy văn bản nhưng không mang document.sign
        body = self.assert_envelope(self.act(doc, "sign"), "PERMISSION_DENIED", 403)
        self.assertEqual(body["details"], {"permission": "document.sign"})
        # người không thấy được văn bản (read_all/assigned đều không) — dù mang permission — nhận 404
        eid, _ = self.db.make_employee(roles=("EMPLOYEE",), grants=("document.approve_content",))
        other = self.doc()
        self.assert_envelope(self.act(other, "approve-content", headers=self.as_user(eid)), "NOT_FOUND", 404)
        self.assertEqual(document_row(self.db, other.document_id)["status"], "PENDING_APPROVAL")

    def test_document_khong_ton_tai_la_404(self):
        r = self.client.post(f"{API}/documents/{uuid.uuid4()}/actions/approve-content", json={"expected_row_version": 1}, headers={**CSRF, **self.h, "Idempotency-Key": str(uuid.uuid4())})
        self.assert_envelope(r, "NOT_FOUND", 404)

    def test_nguoi_thu_huong_bi_chan_d006(self):
        officer, octx = make_officer(self.db, self.pool)
        doc = self.doc(beneficiary=(officer, octx))
        body = self.assert_envelope(self.act(doc, "approve-content", headers=self.as_user(officer)), "SELF_APPROVAL_BLOCKED", 403)
        self.assertNotIn("details", body)
        self.assertEqual(document_row(self.db, doc.document_id)["status"], "PENDING_APPROVAL")
        self.assertEqual(self.act(doc, "approve-content").status_code, 200)  # người khác duyệt được

    def test_ky_chi_nhan_nguoi_duoc_giao(self):
        doc, (signer_id, _), _ = self.pending_signature()
        _, other_ctx = make_officer(self.db, self.pool, signer=True, code="ZZ" + uuid.uuid4().hex[:8])
        body = self.assert_envelope(self.act(doc, "sign", headers=self.as_user(other_ctx.actor.employee_id)), "PERMISSION_DENIED", 403)
        self.assertEqual(body["details"], {"permission": "assignee"})
        r = self.act(doc, "sign", headers=self.as_user(signer_id))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()["kind"], r.json()["document"]["status"], r.json()["request"]["status"]), ("SIGNED", "PENDING_SEAL", "APPROVED"))

    def test_nguoi_ky_vai_tro_signer_ky_duoc_khi_duoc_giao_va_khong_thay_van_ban_khac(self):
        signer, h = self.signer_role()
        mine, other = self.doc(), self.doc()
        for d in (mine, other):
            self.approve(d, self.octx)
        self.assign_signature(mine, signer)
        self.assign_signature(other, self.db.make_employee(roles=("SIGNER",))[0])  # giao cho người khác
        self.assert_envelope(self.act(other, "sign", headers=h), "NOT_FOUND", 404)  # không thấy → 404, không phải 403
        r = self.act(mine, "sign", headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["document"]["status"], "PENDING_SEAL")

    def test_dong_dau_200_va_kiem_page_count_cua_edge_stamp(self):
        doc, _, _ = self.pending_seal(seal_type="EDGE_STAMP")
        body = self.assert_envelope(self.act(doc, "apply-seal", copies_count=1), "VALIDATION_FAILED", 422)
        self.assertEqual(body["details"]["fields"], [{"field": "page_count", "code": "REQUIRED"}])
        body = self.assert_envelope(self.act(doc, "apply-seal", copies_count=1, page_count=1), "VALIDATION_FAILED", 422)
        self.assertEqual(body["details"]["fields"], [{"field": "page_count", "code": "OUT_OF_RANGE"}])
        self.assertEqual(document_row(self.db, doc.document_id)["status"], "PENDING_SEAL")
        r = self.act(doc, "apply-seal", copies_count=2, page_count=3)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()["kind"], r.json()["document"]["status"]), ("SEALED", "SEALED"))
        self.assertEqual(rows(self.db, "select seal_type, copies_count, page_count from seal_action where document_id = %s", doc.document_id), [("EDGE_STAMP", 2, 3)])

    def test_dong_dau_khong_nhan_loai_dau_tu_client_va_so_ban_toi_thieu_mot(self):
        doc, _, _ = self.pending_seal()
        body = self.assert_envelope(self.act(doc, "apply-seal", copies_count=1, seal_type="TITLE_STAMP"), "VALIDATION_FAILED", 422)
        self.assertEqual(body["details"]["fields"], [{"field": "seal_type", "code": "NOT_ALLOWED"}])
        body = self.assert_envelope(self.act(doc, "apply-seal", copies_count=0), "VALIDATION_FAILED", 422)
        self.assertEqual(body["details"]["fields"], [{"field": "copies_count", "code": "OUT_OF_RANGE"}])
        self.assertEqual(scalar(self.db, "select count(*) from seal_action where document_id = %s", doc.document_id), 0)

    def test_phat_hanh_tra_202_issue_in_progress_va_chua_co_so(self):
        doc, _, _ = self.sealed()
        key = uuid.uuid4()
        r = self.act(doc, "issue", key=key)
        self.assertEqual(r.status_code, 202, r.text)
        body = r.json()
        self.assertEqual((body["decision_record_id"], body["kind"]), (str(key), "ISSUE_ORDERED"))
        d = body["document"]
        self.assertEqual((d["status"], d["issue_in_progress"], d["document_number"], d["status_label"], d["issued_date"]), ("SEALED", True, None, "Đang cấp số và phát hành", None))
        again = self.act(doc, "issue", key=key)
        self.assertEqual((again.status_code, again.headers.get("idempotent-replayed")), (202, "true"))  # cùng mã HTTP của lần đầu
        self.assertEqual(scalar(self.db, "select count(*) from document_register_entry where document_id = %s", doc.document_id), 0)  # không cấp số
        self.assertEqual(scalar(self.db, "select count(*) from job where subject_document_id = %s and job_type = 'finalize_issue'", doc.document_id), 1)

    def test_phat_hanh_lenh_thu_hai_va_dang_cho_tiep_quan(self):
        doc, _, _ = self.sealed()
        self.assertEqual(self.act(doc, "issue").status_code, 202)
        body = self.assert_envelope(self.act(doc, "issue"), "STATE_CONFLICT", 409)
        self.assertEqual(body["details"], {"current_status": "SEALED"})
        halted, _, _ = self.sealed()
        with self.db.connect("bo19_migrator") as c:
            c.execute("insert into approval_step (id, document_id, step_kind, status) values (%s, %s, 'TAKEOVER', 'OPEN')", (uuid.uuid4(), halted.document_id))
        self.assert_envelope(self.act(halted, "issue"), "DOCUMENT_AWAITING_TAKEOVER", 409)

    def test_loi_khong_mang_gia_tri(self):
        doc = self.doc()
        responses = [self.act(doc, "approve-content", body={"expected_row_version": 99}), self.act(doc, "sign"), self.act(doc, "issue"), self.act(doc, "apply-seal", copies_count=1)]
        for r in responses:
            self.assertGreaterEqual(r.status_code, 400)
            for secret in (BODY_OK, RES, "NGƯỜI GIẢ", "Ngân hàng GIẢ"):
                self.assertNotIn(secret, r.text)


class VanBanCuaNguoiTao(DocApiBase):
    """`GET /requests/{id}` điền `documents` (`DocumentOwnerView`, B9b2, ADR-041 mục 9): người tạo thấy trạng thái văn bản của mình; số, ngày và `final_render_id` CHỈ từ `ISSUED` trở đi."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with cls.db.connect("bo19_migrator", autocommit=True) as c:
            reg = c.execute("select document_register_id from request_type where code = 'WORK_CONFIRMATION'").fetchone()[0]
            c.execute("insert into document_register_format (id, document_register_id, series, format_pattern, symbol, seq_min_digits, effective_from) "
                      "values (%s, %s, 'TRIAL', 'TRIAL-{seq}/{year}/{symbol}', 'THU-NGHIEM', 3, timestamptz '2020-01-01 00:00:00+00')", (uuid.uuid4(), reg))

    def owner_documents(self, doc, who=None) -> list[dict]:
        r = self.client.get(f"{API}/requests/{doc.request_id}", headers=who or self.as_user(doc.beneficiary_id))
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["documents"]

    def final_render(self, doc) -> uuid.UUID:
        rid = uuid.uuid4()
        with self.db.connect(autocommit=True) as c:
            c.execute("set session_replication_role = replica")
            c.execute("insert into document_render (id, document_id, operating_mode, render_kind, input_hash, template_version_id, revision_round, docx_object_key, pdf_object_key, watermark_text) "
                      "values (%s, %s, 'NON_PRODUCTION', 'FINAL', %s, %s, 0, %s, %s, 'BẢN THỬ NGHIỆM')", (rid, doc.document_id, rid.bytes * 2, doc.version_id, f"renders/{rid}.docx", f"renders/{rid}.pdf"))
        return rid

    def test_chua_co_document_thi_rong(self):
        eid, _ = self.db.make_employee(roles=("EMPLOYEE",))
        from tests.gate_support import ctx_of
        from tests.request_support import build_request

        rid = build_request(self.pool, self.db, eid, ctx_of(self.pool, eid))
        r = self.client.get(f"{API}/requests/{rid}", headers=self.as_user(eid))
        self.assertEqual((r.json()["documents"], r.json()["changes_requested"]), ([], None))

    def test_theo_doi_tu_cho_duyet_toi_dang_hoan_tat_phat_hanh_roi_issued(self):
        from bo19.tool_layer.numbering import document_number_assign
        from bo19.tool_layer.tools.document_transition import document_mark_issued
        import datetime as dt

        self.officer(signer=True)
        doc = self.doc()
        got = self.owner_documents(doc)
        self.assertEqual(got, [{"id": str(doc.document_id), "status": "PENDING_APPROVAL", "status_label": "Chờ duyệt nội dung", "issue_in_progress": False,
                                "document_number": None, "issued_date": None, "final_render_id": None}])
        self.approve(doc, self.octx)
        self.route(doc)
        signer_id = document_row(self.db, doc.document_id)["signer_employee_id"]
        from tests.gate_support import ctx_of

        self.sign(doc, ctx_of(self.pool, signer_id))
        self.seal(doc, self.octx)
        self.assertEqual([(d["status"], d["issue_in_progress"]) for d in self.owner_documents(doc)], [("SEALED", False)])
        order = self.issue(doc, self.octx).decision_record_id
        (mid,) = self.owner_documents(doc)
        self.assertEqual((mid["status"], mid["issue_in_progress"], mid["status_label"], mid["document_number"], mid["final_render_id"]), ("SEALED", True, "Đang cấp số và phát hành", None, None))
        entry = document_number_assign(self.pool, self.sys, document_id=doc.document_id, issue_decision_id=order)
        (mid,) = self.owner_documents(doc)
        self.assertEqual((mid["issue_in_progress"], mid["document_number"]), (True, None))  # đoạn 2: đã có số trong sổ nhưng văn bản chưa phát hành — KHÔNG lộ số
        render = self.final_render(doc)
        document_mark_issued(self.pool, self.sys, document_id=doc.document_id, issue_decision_id=order, entry_id=entry.entry_id, render_id=render, issued_date=dt.date(2026, 3, 9))
        (done,) = self.owner_documents(doc)
        self.assertEqual((done["status"], done["status_label"], done["issue_in_progress"], done["document_number"], done["issued_date"], done["final_render_id"]),
                         ("ISSUED", "Đã phát hành", False, entry.formatted_number, "2026-03-09", str(render)))
        detail = self.client.get(f"{API}/requests/{doc.request_id}", headers=self.as_user(doc.beneficiary_id)).json()
        self.assertEqual(detail["status"], "FULFILLED")

    def test_nguoi_khac_khong_thay(self):
        doc = self.doc()
        stranger, _ = self.db.make_employee(roles=("EMPLOYEE",))
        r = self.client.get(f"{API}/requests/{doc.request_id}", headers=self.as_user(stranger))
        self.assertEqual(r.status_code, 404)
        self.assertNotIn(str(doc.document_id), r.text)


class HopDongKhopOpenapi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
        cls.schemas = cls.spec["components"]["schemas"]

    def fields(self, name: str) -> tuple[set[str], set[str]]:
        spec = self.schemas[name]
        props, required = set(spec.get("properties", {})), set(spec.get("required", []))
        for part in spec.get("allOf", []):
            sub_props, sub_req = self.fields(part["$ref"].rsplit("/", 1)[1]) if "$ref" in part else (set(part.get("properties", {})), set(part.get("required", [])))
            props |= sub_props
            required |= sub_req
        return props, required

    def test_model_khop_schema(self):
        for model, name in ((schemas.DocumentSummaryOut, "DocumentSummary"), (schemas.ReviewQueueItemOut, "ReviewQueueItem"), (schemas.ReviewQueuePageOut, "ReviewQueuePage"),
                            (schemas.DocumentReviewViewOut, "DocumentReviewView"), (schemas.TemplateRefOut, "TemplateRef"), (schemas.VariableViewOut, "VariableView"),
                            (schemas.RenderRefOut, "RenderRef"), (schemas.ApprovalStepViewOut, "ApprovalStepView"), (schemas.DecisionTextViewOut, "DecisionTextView"),
                            (schemas.DecisionViewOut, "DecisionView"), (schemas.ApproveContentBody, "ApproveContentBody"), (schemas.SignBody, "SignBody"),
                            (schemas.ApplySealBody, "ApplySealBody"), (schemas.IssueBody, "IssueBody")):
            with self.subTest(schema=name):
                props, required = self.fields(name)
                self.assertEqual(set(model.model_fields), props)
                self.assertTrue(required <= props)

    def test_review_queue_status_co_approved_cua_sprint_1(self):
        self.assertEqual(self.schemas["ReviewQueueStatus"]["enum"], ["PENDING_APPROVAL", "PENDING_SIGNATURE", "PENDING_SEAL", "APPROVED"])

    def test_bon_thao_tac_cong_khai_dung_permission_va_job(self):
        want = {"approve-content": ("document.approve_content", "resume_document_graph"), "sign": ("document.sign", "resume_document_graph"),
                "apply-seal": ("document.apply_seal", "resume_document_graph"), "issue": ("document.issue", "finalize_issue")}
        for action, (permission, job) in want.items():
            op = self.spec["paths"][f"/documents/{{document_id}}/actions/{action}"]["post"]
            self.assertEqual((op["x-bo19-permission"], op["x-bo19-enqueues"]), ([permission], [job]), action)


if __name__ == "__main__":
    unittest.main()
