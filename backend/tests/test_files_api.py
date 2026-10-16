"""Hai endpoint tải file (B8b; mục Tải file của 05-api.md, ADR-014, AC-1.3) qua ASGI app thật, PostgreSQL và SeaweedFS 4.47 THẬT, role `bo19_app`.

Điều được chứng minh, nói bằng hành vi:
- **ma trận quyền:** `request.read_all` — mọi bản, cả hai định dạng; `request.read_assigned` — chỉ khi có `approval_step` giao cho mình trên văn bản đó (không phải bước đã huỷ, không phải văn bản khác); người tạo yêu cầu —
  CHỈ bản `FINAL`, CHỈ `pdf`, CHỈ khi đã `ISSUED` hoặc sau đó, CHỈ bản `final_render_id` trỏ tới: `.docx`, bản nháp, bản chưa phát hành, bản `FINAL` rơi rớt → `PERMISSION_DENIED`; người không liên quan và render không tồn tại →
  `NOT_FOUND` cùng thân; chưa đăng nhập → 401;
- **so checksum trước byte đầu tiên:** object bị sửa hay mất, hay quá trần kích thước, hay storage chưa cấu hình → cùng `FILE_UNAVAILABLE` 503, thân không nói lý do; response lỗi không chứa byte của file;
- **response:** đúng byte, `Content-Type` theo định dạng, `Cache-Control: no-store`, `Content-Disposition: attachment` với tên chỉ gồm id, `X-Content-Type-Options: nosniff`;
- **`audit_event`:** mỗi lần tải thành công một dòng `document.file_fetch` (mã, kích thước, người tải); lần hỏng một dòng mức `WARNING`; không tên file, không byte;
- **bản gốc template:** chỉ `template.manage`; version không thuộc template đó → `NOT_FOUND`.

Cần BO19_TEST_PG_SUPERUSER_DSN và BO19_TEST_S3_ENDPOINT. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_files_api -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import datetime as dt
import unittest
import uuid
from unittest import mock

from fastapi.testclient import TestClient

from bo19.api.app import create_app
from bo19.api.deps.state import AppState
from bo19.api.files_gate import FileFetchLimits
from bo19.tool_layer import storage as st
from tests.auth_support import SECRET, AuthBase
from tests.s3_support import ENDPOINT, REQUIRED, admin_client, drop_bucket, new_bucket, storage_for

API = "/api/v1"
PDF, DOCX = b"%PDF-1.7 gia " + b"p" * 200, b"PK gia-docx " + b"d" * 200


class FilesBase(AuthBase):
    @classmethod
    def setUpClass(cls):
        if not ENDPOINT:
            if REQUIRED:
                raise AssertionError("BO19_REQUIRE_S3=1 nhưng thiếu BO19_TEST_S3_ENDPOINT")
            raise unittest.SkipTest("cần BO19_TEST_S3_ENDPOINT")
        super().setUpClass()

    def setUp(self):
        super().setUp()
        self.bucket = new_bucket()
        self.addCleanup(drop_bucket, self.bucket)
        self.storage = storage_for(self.bucket)
        self.raw = admin_client()
        self.rebuild(self.storage)
        self.creator, _ = self.employee(roles=("EMPLOYEE",))
        self.officer, _ = self.employee(roles=("ADMIN_OFFICER",))
        self.signer, _ = self.employee(roles=("SIGNER",))
        self.other, _ = self.employee(roles=("EMPLOYEE",))

    def rebuild(self, storage, file_fetch: FileFetchLimits | None = None):
        self.app = create_app(AppState(pool=self.pool, session_secret=SECRET, verifier=self.verifier, storage=storage, file_fetch=file_fetch or FileFetchLimits()))
        self.client = TestClient(self.app, raise_server_exceptions=False, base_url="https://testserver", client=(self.ip, 50000))

    def put(self, key: str, data: bytes, purpose: str) -> None:
        st.put_once(self.pool, self.storage, object_key=key, purpose=purpose, content_type="application/octet-stream", data=data, lease_s=120)

    def make_render(self, *, kind: str = "FINAL", doc_status: str = "ISSUED", pinned: bool = True, force_pin: bool = False, creator: uuid.UUID | None = None, pdf: bytes = PDF) -> tuple[uuid.UUID, uuid.UUID]:
        """(document_id, render_id) với object THẬT trong bucket. `doc_status` ISSUED kéo theo mọi cột mà ràng buộc đòi — id giả dưới `replica`."""
        did, rid, req, ver, tid = (uuid.uuid4() for _ in range(5))
        docx_key, pdf_key = f"renders/{did}/h.docx", f"renders/{did}/h.pdf"
        self.put(docx_key, DOCX, "RENDER_DOCX")
        self.put(pdf_key, pdf, "RENDER_PDF")
        now = dt.datetime.now(dt.timezone.utc)
        issued = doc_status in ("ISSUED", "REVOKED", "SUPERSEDED")
        with self.db.connect(autocommit=True) as c:
            c.execute("set session_replication_role = replica")
            c.execute("insert into request (id, request_type_code, status, created_by_employee_id, beneficiary_employee_id) values (%s, 'WORK_CONFIRMATION', 'IN_REVIEW', %s, %s)", (req, creator or self.creator, creator or self.creator))
            c.execute("insert into template (id, code, request_type_code, name) values (%s, %s, 'WORK_CONFIRMATION', 'MẪU GIẢ')", (tid, f"G_{uuid.uuid4().hex[:8]}"))
            c.execute("insert into template_version (id, template_id, version_no, status, source_object_key, uploaded_by_employee_id, required_fonts, activated_at) values (%s, %s, 1, 'ACTIVE', %s, %s, %s, now())",
                      (ver, tid, docx_key, self.creator, ["Times New Roman"]))
            c.execute("insert into document (id, request_id, template_version_id, status, operating_mode, requires_seal, approved_content_hash, approved_decision_id, approved_render_id, "
                      "signer_employee_id, final_render_id, issued_register_entry_id, issued_date, issued_at) values (%s, %s, %s, %s, 'NON_PRODUCTION', false, %s, %s, %s, %s, %s, %s, %s, %s)",
                      (did, req, ver, doc_status, b"\x00" * 32 if doc_status not in ("DRAFT", "PENDING_APPROVAL") else None, uuid.uuid4() if doc_status not in ("DRAFT", "PENDING_APPROVAL") else None,
                       uuid.uuid4() if doc_status not in ("DRAFT", "PENDING_APPROVAL") else None, self.signer if doc_status not in ("DRAFT", "PENDING_APPROVAL") else None,
                       rid if (issued and pinned) or force_pin else (uuid.uuid4() if issued else None), uuid.uuid4() if issued else None, now.date() if issued else None, now if issued else None))
            c.execute("insert into document_render (id, document_id, operating_mode, render_kind, input_hash, template_version_id, revision_round, docx_object_key, pdf_object_key, watermark_text) "
                      "values (%s, %s, 'NON_PRODUCTION', %s, %s, %s, 0, %s, %s, 'BẢN THỬ NGHIỆM — KHÔNG CÓ GIÁ TRỊ PHÁP LÝ')", (rid, did, kind, uuid.uuid4().bytes * 2, ver, docx_key, pdf_key))  # `ck_document_render_watermark` (0014): NON_PRODUCTION phải có chuỗi
        self.version_of = {did: (tid, ver)}
        return did, rid

    def assign(self, did: uuid.UUID, employee: uuid.UUID, status: str = "OPEN") -> None:
        with self.db.connect(autocommit=True) as c:
            c.execute("set session_replication_role = replica")
            c.execute("insert into approval_step (id, document_id, step_kind, assignee_employee_id, status, closed_at) values (%s, %s, 'CONTENT_REVIEW', %s, %s, %s)",
                      (uuid.uuid4(), did, employee, status, None if status == "OPEN" else dt.datetime.now(dt.timezone.utc)))

    def get(self, did, rid, fmt, who):
        return self.client.get(f"{API}/documents/{did}/renders/{rid}/file", params={"format": fmt}, headers=self.as_user(who))

    def audits(self, rid) -> list[tuple]:
        with self.db.connect("bo19_migrator") as c:
            return c.execute("select action, severity, actor_employee_id, payload from audit_event where entity_id = %s order by occurred_at", (str(rid),)).fetchall()


class Quyen(FilesBase):
    def test_nguoi_tao_chi_tai_duoc_pdf_ban_final_sau_khi_phat_hanh(self):
        did, rid = self.make_render()
        r = self.get(did, rid, "pdf", self.creator)
        self.assertEqual((r.status_code, r.content), (200, PDF), r.text[:200])

    def test_nguoi_tao_khong_tai_duoc_docx_ban_nhap_hay_ban_chua_phat_hanh(self):
        for label, kw, fmt in (("docx của bản FINAL", {}, "docx"), ("bản nháp", {"kind": "DRAFT"}, "pdf"), ("bản nháp docx", {"kind": "DRAFT"}, "docx"),
                               ("văn bản chưa phát hành", {"doc_status": "PENDING_APPROVAL"}, "pdf"), ("FINAL đã ghim nhưng văn bản chưa phát hành", {"doc_status": "PENDING_APPROVAL", "force_pin": True}, "pdf"), ("FINAL rơi rớt không được ghim", {"pinned": False}, "pdf")):
            did, rid = self.make_render(**kw)
            r = self.get(did, rid, fmt, self.creator)
            self.assert_envelope(r, "PERMISSION_DENIED", 403)
            self.assertNotIn(b"PK", r.content, label)
            self.assertNotIn(b"%PDF", r.content, label)

    def test_nguoi_tao_tai_duoc_khi_van_ban_da_bi_thu_hoi_hay_thay_the(self):
        for status in ("REVOKED", "SUPERSEDED"):
            did, rid = self.make_render(doc_status=status)
            self.assertEqual(self.get(did, rid, "pdf", self.creator).status_code, 200, status)

    def test_can_bo_hanh_chinh_tai_moi_ban_ca_hai_dinh_dang(self):
        for kind, status in (("DRAFT", "PENDING_APPROVAL"), ("FINAL", "ISSUED")):
            did, rid = self.make_render(kind=kind, doc_status=status)
            self.assertEqual(self.get(did, rid, "docx", self.officer).content, DOCX)
            self.assertEqual(self.get(did, rid, "pdf", self.officer).content, PDF)

    def test_read_assigned_chi_khi_co_buoc_duyet_giao_cho_minh_tren_van_ban_do(self):
        did, rid = self.make_render(kind="DRAFT", doc_status="PENDING_APPROVAL")
        self.assert_envelope(self.get(did, rid, "pdf", self.signer), "NOT_FOUND", 404)  # có permission nhưng chưa được giao
        self.assign(did, self.signer)
        self.assertEqual(self.get(did, rid, "pdf", self.signer).content, PDF)
        self.assertEqual(self.get(did, rid, "docx", self.signer).content, DOCX)
        other_doc, other_render = self.make_render(kind="DRAFT", doc_status="PENDING_APPROVAL")
        self.assert_envelope(self.get(other_doc, other_render, "pdf", self.signer), "NOT_FOUND", 404)  # bước được giao ở văn bản KHÁC không mở văn bản này

    def test_buoc_da_quyet_van_xem_duoc_buoc_da_huy_thi_khong(self):
        did, rid = self.make_render(kind="DRAFT", doc_status="PENDING_APPROVAL")
        self.assign(did, self.signer, status="CANCELLED")
        self.assert_envelope(self.get(did, rid, "pdf", self.signer), "NOT_FOUND", 404)
        self.assign(did, self.signer, status="DECIDED")
        self.assertEqual(self.get(did, rid, "pdf", self.signer).content, PDF)

    def test_nguoi_duoc_giao_ma_khong_co_permission_read_assigned_thi_khong(self):
        did, rid = self.make_render(kind="DRAFT", doc_status="PENDING_APPROVAL")
        self.assign(did, self.other)  # `other` chỉ là EMPLOYEE
        self.assert_envelope(self.get(did, rid, "pdf", self.other), "NOT_FOUND", 404)

    def test_nguoi_khong_lien_quan_va_render_khong_ton_tai_cung_mot_ma_va_cung_than(self):
        did, rid = self.make_render()
        a = self.get(did, rid, "pdf", self.other)
        b = self.get(did, uuid.uuid4(), "pdf", self.officer)
        c = self.get(uuid.uuid4(), rid, "pdf", self.officer)  # render có thật nhưng sai văn bản
        for r in (a, b, c):
            self.assert_envelope(r, "NOT_FOUND", 404)
        self.assertEqual({k: v for k, v in a.json().items() if k != "trace_id"}, {k: v for k, v in b.json().items() if k != "trace_id"})

    def test_chua_dang_nhap_va_format_la(self):
        did, rid = self.make_render()
        self.assert_envelope(self.client.get(f"{API}/documents/{did}/renders/{rid}/file", params={"format": "pdf"}), "UNAUTHENTICATED", 401)
        self.assertEqual(self.client.get(f"{API}/documents/{did}/renders/{rid}/file", params={"format": "xlsx"}, headers=self.as_user(self.officer)).status_code, 422)
        self.assertEqual(self.client.get(f"{API}/documents/{did}/renders/{rid}/file", headers=self.as_user(self.officer)).status_code, 422)  # format bắt buộc


class Response(FilesBase):
    def test_header_va_ten_file_chi_mang_id(self):
        did, rid = self.make_render()
        r = self.get(did, rid, "pdf", self.officer)
        self.assertEqual(r.headers["content-type"], "application/pdf")
        self.assertEqual(r.headers["cache-control"], "no-store")
        self.assertEqual(r.headers["x-content-type-options"], "nosniff")
        self.assertEqual(r.headers["content-disposition"], f'attachment; filename="{did}-final.pdf"')
        d = self.get(did, rid, "docx", self.officer)
        self.assertEqual(d.headers["content-type"], "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        self.assertTrue(d.headers["content-disposition"].endswith(f'{did}-final.docx"'))

    def test_checksum_lech_hay_mat_object_hay_qua_tran_cung_mot_ma_khong_ro_ly_do(self):
        bodies = []
        for label in ("sửa", "mất", "quá trần"):
            did, rid = self.make_render()
            key = f"renders/{did}/h.pdf"
            if label == "sửa":
                self.raw.put_object(Bucket=self.bucket, Key=key, Body=b"%PDF-1.7 BYTE-DA-BI-SUA")
                r = self.get(did, rid, "pdf", self.officer)
            elif label == "mất":
                self.raw.delete_object(Bucket=self.bucket, Key=key)
                r = self.get(did, rid, "pdf", self.officer)
            else:
                with mock.patch("bo19.tool_layer.endpoint_ops.files.wv.FILE_FETCH_MAX_BYTES", 10):
                    r = self.get(did, rid, "pdf", self.officer)
            body = self.assert_envelope(r, "FILE_UNAVAILABLE", 503)
            self.assertNotIn(b"BYTE-DA-BI-SUA", r.content)
            self.assertNotIn(b"%PDF", r.content)
            bodies.append({k: v for k, v in body.items() if k != "trace_id"})
        self.assertEqual(bodies[0], bodies[1])
        self.assertEqual(bodies[1], bodies[2])  # client không phân biệt được đã mất, đã bị sửa hay quá lớn

    def test_storage_chua_cau_hinh_la_file_unavailable(self):
        did, rid = self.make_render()
        self.rebuild(None)
        self.assert_envelope(self.get(did, rid, "pdf", self.officer), "FILE_UNAVAILABLE", 503)

    def test_byte_dau_tien_chi_ra_sau_khi_kiem_checksum(self):
        """`fetch` đọc cả object và kiểm trước khi trả: nếu kiểm hỏng thì `Response` không bao giờ được dựng."""
        did, rid = self.make_render()
        with mock.patch("bo19.api.routers.files.DeadlineStreamingResponse", side_effect=AssertionError("đã dựng response trước khi kiểm")):
            self.raw.put_object(Bucket=self.bucket, Key=f"renders/{did}/h.pdf", Body=b"sai")
            self.assert_envelope(self.get(did, rid, "pdf", self.officer), "FILE_UNAVAILABLE", 503)


class Audit(FilesBase):
    def test_moi_lan_tai_mot_dong_chi_mang_ma(self):
        did, rid = self.make_render()
        self.get(did, rid, "pdf", self.officer)
        self.get(did, rid, "docx", self.officer)
        rows = self.audits(rid)
        self.assertEqual([r[0] for r in rows], ["document.file_fetch"] * 2)
        self.assertEqual([r[1] for r in rows], ["INFO", "INFO"])
        self.assertEqual({r[2] for r in rows}, {self.officer})
        self.assertEqual([(r[3]["format"], r[3]["render_kind"], r[3]["outcome"]) for r in rows], [("pdf", "FINAL", "OK"), ("docx", "FINAL", "OK")])
        self.assertEqual(rows[0][3]["size_bytes"], len(PDF))
        for r in rows:
            self.assertNotIn("filename", str(r[3]))

    def test_lan_hong_van_de_dau_vet_muc_warning(self):
        did, rid = self.make_render()
        self.raw.delete_object(Bucket=self.bucket, Key=f"renders/{did}/h.pdf")
        self.get(did, rid, "pdf", self.officer)
        rows = self.audits(rid)
        self.assertEqual([(r[0], r[1], r[3]["outcome"]) for r in rows], [("document.file_fetch", "WARNING", "FILE_UNAVAILABLE")])
        self.assertNotIn("MISSING", str(rows[0][3]))  # lý do chi tiết chỉ ở log

    def test_bi_tu_choi_khong_de_lai_dong_tai(self):
        did, rid = self.make_render(kind="DRAFT")
        self.get(did, rid, "pdf", self.creator)
        self.assertEqual(self.audits(rid), [])


class BanGocTemplate(FilesBase):
    def url(self, tid, vid):
        return f"{API}/templates/{tid}/versions/{vid}/source"

    def test_chi_template_manage_tai_duoc(self):
        did, rid = self.make_render()
        tid, vid = self.version_of[did]
        self.assertEqual(self.client.get(self.url(tid, vid), headers=self.as_user(self.officer)).content, DOCX)
        r = self.client.get(self.url(tid, vid), headers=self.as_user(self.creator))
        self.assert_envelope(r, "PERMISSION_DENIED", 403)
        self.assertEqual(r.json()["details"], {"permission": "template.manage"})

    def test_version_khong_thuoc_template_hoac_khong_ton_tai(self):
        did, rid = self.make_render()
        tid, vid = self.version_of[did]
        self.assert_envelope(self.client.get(self.url(uuid.uuid4(), vid), headers=self.as_user(self.officer)), "NOT_FOUND", 404)
        self.assert_envelope(self.client.get(self.url(tid, uuid.uuid4()), headers=self.as_user(self.officer)), "NOT_FOUND", 404)

    def test_audit_template_source_fetch(self):
        did, rid = self.make_render()
        tid, vid = self.version_of[did]
        self.client.get(self.url(tid, vid), headers=self.as_user(self.officer))
        with self.db.connect("bo19_migrator") as c:
            rows = c.execute("select action, entity_type, payload from audit_event where entity_id = %s", (str(vid),)).fetchall()
        self.assertEqual([(r[0], r[1], r[2]["outcome"]) for r in rows], [("template_version.source_fetch", "template_version", "OK")])


if __name__ == "__main__":
    unittest.main()
