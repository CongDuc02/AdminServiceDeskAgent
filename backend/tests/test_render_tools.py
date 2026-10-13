"""Tool `docx_render`, `pdf_export` và `storage.fetch` (B8b) — PostgreSQL, SeaweedFS 4.47 và `soffice` THẬT.

Điều được chứng minh, nói bằng hành vi:
- **`docx_render`:** khoá `renders/{document_id}/{input_hash}.docx` theo INPUT; ghi một lần (gọi lại: `reused`, không `PUT`, không điền lại); input khác thì khoá khác và bản cũ còn nguyên; chế độ và phiên bản template đọc từ `document`
  (watermark theo chế độ đã ghim, không nhận từ người gọi); `MISSING_VARIABLE`/`UNKNOWN_VARIABLE`/`TEMPLATE_NOT_ACTIVE`/`DOCUMENT_NOT_FOUND`, và KHÔNG ghi gì khi lỗi; chỉ tác nhân hệ thống;
- **`pdf_export`:** `FONT_MISSING` TRƯỚC khi gọi `soffice`; chuyển đổi xong RỒI MỚI giành khoá (ADR-015); khoá đã có commit thì không chuyển đổi lại, kể cả khi bộ chuyển đổi không tất định; dòng `document_render` chỉ thêm khi cả hai object
  đã commit và idempotent; hai worker cùng input: một dòng, một PDF;
- **`audit_event`** `document.docx_render`, `document.pdf_export`: mã và tham chiếu, không giá trị biến;
- **`storage.fetch`:** kiểm checksum trước khi trả byte; object bị sửa, mất, quá trần, chưa commit hay storage không với tới đều là `FILE_UNAVAILABLE` (lý do chỉ để log).

Cần BO19_TEST_PG_SUPERUSER_DSN, BO19_TEST_S3_ENDPOINT, `soffice`, `pdftotext` (image target `test`; CI đặt BO19_REQUIRE_S3=1 và BO19_REQUIRE_SOFFICE=1).
Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_render_tools -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import hashlib
import json
import threading
import unittest
import uuid
from unittest import mock

from bo19.config import working_values as wv
from bo19.persistence.pool import Pool
from bo19.tool_layer import storage as st
from bo19.tool_layer.kernel.context import Actor, ToolContext
from bo19.tool_layer.kernel.permission import SystemActorRequired, system_context
from bo19.tool_layer.rendering import convert
from bo19.tool_layer.tools import docx_render as dr
from bo19.tool_layer.tools import pdf_export as pe
from tests import pg_support
from tests.render_support import DECLARED, VALUES, build_template, docx_text, pdf_text, require_tool
from tests.s3_support import ENDPOINT, REQUIRED, admin_client, drop_bucket, new_bucket, storage_for

SRC_PURPOSE = "TEMPLATE_SOURCE"


@unittest.skipUnless(pg_support.SUPERUSER_DSN, "cần BO19_TEST_PG_SUPERUSER_DSN")
class RenderBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ENDPOINT:
            if REQUIRED:
                raise AssertionError("BO19_REQUIRE_S3=1 nhưng thiếu BO19_TEST_S3_ENDPOINT")
            raise unittest.SkipTest("cần BO19_TEST_S3_ENDPOINT")
        require_tool(cls, "soffice")
        require_tool(cls, "pdftotext")
        cls.db = pg_support.PgDb(pg_support.SUPERUSER_DSN)
        cls.pool = Pool(cls.db.dsn("bo19_app"), application_name="bo19-test-render", min_size=1, max_size=8)
        cls.pool.open()

    @classmethod
    def tearDownClass(cls):
        cls.pool.close()
        cls.db.drop()

    def setUp(self):
        self.bucket = new_bucket()
        self.addCleanup(drop_bucket, self.bucket)
        self.storage = storage_for(self.bucket)
        self.raw = admin_client()
        self.sys = system_context()

    # ---- dữ liệu thử (siêu người dùng + replica: không dựng cả chuỗi nhân viên/yêu cầu; khoá ngoại của `bo19_app` vẫn thật khi tool chạy) ----

    def make_template(self, *, status: str = "ACTIVE", fonts: tuple[str, ...] = ("Times New Roman",), template: bytes | None = None) -> uuid.UUID:
        data = template or build_template()
        key = f"templates/{uuid.uuid4()}/source.docx"
        st.put_once(self.pool, self.storage, object_key=key, purpose=SRC_PURPOSE, content_type="application/octet-stream", data=data, lease_s=120)
        tid, vid = uuid.uuid4(), uuid.uuid4()
        with self.db.connect(autocommit=True) as c:
            c.execute("set session_replication_role = replica")
            c.execute("insert into template (id, code, request_type_code, name) values (%s, %s, 'WORK_CONFIRMATION', 'MẪU GIẢ')", (tid, f"GIA_{uuid.uuid4().hex[:8]}"))
            c.execute("insert into template_version (id, template_id, version_no, status, source_object_key, uploaded_by_employee_id, required_fonts, activated_at, retired_at) "
                      "values (%s, %s, 1, %s, %s, %s, %s, %s, %s)",
                      (vid, tid, status, key, uuid.uuid4(), list(fonts), None if status == "UPLOADED" else "2026-01-01T00:00:00+00", "2026-02-01T00:00:00+00" if status == "RETIRED" else None))
            for name in DECLARED:
                c.execute("insert into template_variable (template_version_id, variable_name, kind) values (%s, %s, 'SYSTEM')", (vid, name))
        return vid

    def make_document(self, version_id: uuid.UUID, *, mode: str = "NON_PRODUCTION", revision_round: int = 0) -> uuid.UUID:
        rid, did = uuid.uuid4(), uuid.uuid4()
        with self.db.connect(autocommit=True) as c:
            c.execute("set session_replication_role = replica")
            c.execute("insert into request (id, request_type_code, status, created_by_employee_id, beneficiary_employee_id) values (%s, 'WORK_CONFIRMATION', 'DRAFT', %s, %s)", (rid, uuid.uuid4(), uuid.uuid4()))
            c.execute("insert into document (id, request_id, template_version_id, status, operating_mode, revision_round) values (%s, %s, %s, 'DRAFT', %s, %s)", (did, rid, version_id, mode, revision_round))
        return did

    def scalar(self, sql: str, *args):
        with self.db.connect("bo19_migrator") as c:
            return c.execute(sql, args).fetchone()[0]

    def rows(self, sql: str, *args) -> list[tuple]:
        with self.db.connect("bo19_migrator") as c:
            return c.execute(sql, args).fetchall()

    def render_docx(self, did: uuid.UUID, values=None, kind: str = "DRAFT", storage=None) -> dr.DocxRender:
        return dr.docx_render(self.pool, storage or self.storage, self.sys, document_id=did, render_kind=kind, values=values or VALUES)

    def s3_bytes(self, key: str) -> bytes:
        return self.raw.get_object(Bucket=self.bucket, Key=key)["Body"].read()


class InputHash(unittest.TestCase):
    """Khoá theo INPUT (mục 5.6 của 03-agents.md): phụ thuộc đúng ba thứ — phiên bản template, bảng giá trị, chế độ — và không thứ nào khác."""

    V = uuid.UUID("11111111-1111-4111-8111-111111111111")

    def test_phu_thuoc_tung_trong_ba_thanh_phan(self):
        base = dr.input_hash(self.V, {"a": "1"}, "NON_PRODUCTION")
        self.assertNotEqual(base, dr.input_hash(uuid.uuid4(), {"a": "1"}, "NON_PRODUCTION"))
        self.assertNotEqual(base, dr.input_hash(self.V, {"a": "2"}, "NON_PRODUCTION"))
        self.assertNotEqual(base, dr.input_hash(self.V, {"a": "1", "b": ""}, "NON_PRODUCTION"))
        self.assertNotEqual(base, dr.input_hash(self.V, {"a": "1"}, "PRODUCTION"))

    def test_tat_dinh_va_khong_phu_thuoc_thu_tu(self):
        self.assertEqual(dr.input_hash(self.V, {"a": "1", "b": "2"}, "PRODUCTION"), dr.input_hash(self.V, {"b": "2", "a": "1"}, "PRODUCTION"))
        self.assertEqual(len(dr.input_hash(self.V, {}, "PRODUCTION")), 32)

    def test_tieng_viet_khong_bi_escape_va_khoa_la_hex_64(self):
        h = dr.input_hash(self.V, {"a": "Đặng"}, "PRODUCTION")
        key = dr.render_key(uuid.UUID(int=5), h, "pdf")
        self.assertEqual(key, f"renders/{uuid.UUID(int=5)}/{h.hex()}.pdf")
        self.assertRegex(key, r"^renders/[0-9a-f-]{36}/[0-9a-f]{64}\.pdf$")


class DocxRender(RenderBase):
    def test_ghi_docx_theo_khoa_input_va_dien_dung_bien(self):
        did = self.make_document(self.make_template())
        r = self.render_docx(did)
        self.assertEqual((r.reused, r.render_kind, r.operating_mode, r.revision_round), (False, "DRAFT", "NON_PRODUCTION", 0))
        self.assertEqual(r.docx_key, f"renders/{did}/{r.input_hash.hex()}.docx")
        data = self.s3_bytes(r.docx_key)
        self.assertEqual(hashlib.sha256(data).digest(), r.docx_checksum)
        text = docx_text(data)
        for v in VALUES.values():
            self.assertIn(v, text)
        self.assertEqual(bytes(self.scalar("select checksum_sha256 from stored_object_commit where object_key = %s", r.docx_key)), r.docx_checksum)

    def test_watermark_theo_che_do_da_ghim_trong_document(self):
        version = self.make_template()
        np_doc, prod_doc = self.make_document(version, mode="NON_PRODUCTION"), self.make_document(version, mode="PRODUCTION")
        self.assertIn("THỬ NGHIỆM", docx_text(self.s3_bytes(self.render_docx(np_doc).docx_key)))
        prod = self.render_docx(prod_doc)
        self.assertEqual(prod.operating_mode, "PRODUCTION")
        self.assertNotIn("THỬ NGHIỆM", docx_text(self.s3_bytes(prod.docx_key)))

    def test_khong_co_tham_so_che_do_trong_chu_ky_tool(self):
        import inspect
        self.assertEqual(set(inspect.signature(dr.docx_render).parameters), {"pool", "storage", "ctx", "document_id", "render_kind", "values", "lease_s"})

    def test_goi_lai_cung_input_khong_dien_lai_khong_ghi_lai(self):
        did = self.make_document(self.make_template())
        first = self.render_docx(did)
        with mock.patch.object(dr.docx_fill, "fill_docx", side_effect=AssertionError("không được điền lại")), mock.patch.object(self.storage.__class__, "put_if_absent", side_effect=AssertionError("không được PUT lại")):
            second = self.render_docx(did)
        self.assertEqual((second.reused, second.docx_key, second.docx_checksum), (True, first.docx_key, first.docx_checksum))
        self.assertEqual(self.scalar("select count(*) from stored_object where object_key = %s", first.docx_key), 1)

    def test_input_khac_thi_khoa_khac_va_ban_cu_con_nguyen(self):
        did = self.make_document(self.make_template())
        a = self.render_docx(did)
        b = self.render_docx(did, {**VALUES, "noi_dung": "Nội dung đã sửa ở vòng sau"})
        self.assertNotEqual(a.docx_key, b.docx_key)
        self.assertIn(VALUES["noi_dung"], docx_text(self.s3_bytes(a.docx_key)))
        self.assertIn("Nội dung đã sửa", docx_text(self.s3_bytes(b.docx_key)))

    def test_khoa_khong_phu_thuoc_thu_tu_khoa_cua_bang_gia_tri(self):
        did = self.make_document(self.make_template())
        self.assertEqual(self.render_docx(did, dict(reversed(list(VALUES.items())))).docx_key, self.render_docx(did).docx_key)

    def test_thieu_hoac_thua_bien_khong_ghi_gi(self):
        did = self.make_document(self.make_template())
        with self.assertRaises(dr.docx_fill.MissingVariable) as m:
            self.render_docx(did, {k: v for k, v in VALUES.items() if k != "ho_ten"})
        self.assertEqual(m.exception.names, ("ho_ten",))
        with self.assertRaises(dr.docx_fill.UnknownVariable) as u:
            self.render_docx(did, {**VALUES, "bien_la": "GIÁ-TRỊ-BÍ-MẬT"})
        self.assertNotIn("BÍ-MẬT", f"{u.exception!r}")
        self.assertEqual(self.scalar("select count(*) from stored_object where object_key like %s", f"renders/{did}/%"), 0)
        self.assertEqual(self.scalar("select count(*) from audit_event where document_id = %s", did), 0)

    def test_phien_ban_template_khong_hoat_dong(self):
        for status, kind, ok in (("UPLOADED", "DRAFT", False), ("RETIRED", "DRAFT", False), ("ACTIVE", "DRAFT", True), ("ACTIVE", "FINAL", True), ("RETIRED", "FINAL", True), ("UPLOADED", "FINAL", False)):
            did = self.make_document(self.make_template(status=status))
            if ok:
                self.assertEqual(self.render_docx(did, kind=kind).render_kind, kind, (status, kind))
            else:
                with self.assertRaises(dr.TemplateNotActive, msg=(status, kind)):
                    self.render_docx(did, kind=kind)

    def test_document_khong_ton_tai_va_render_kind_la(self):
        with self.assertRaises(dr.DocumentNotFound):
            self.render_docx(uuid.uuid4())
        did = self.make_document(self.make_template())
        with self.assertRaises(ValueError):
            self.render_docx(did, kind="PREVIEW")

    def test_chi_tac_nhan_he_thong(self):
        did = self.make_document(self.make_template())
        human = ToolContext.create(Actor.employee(uuid.uuid4(), {"document.issue", "template.manage", "request.read_all"}))
        with self.assertRaises(SystemActorRequired):
            dr.docx_render(self.pool, self.storage, human, document_id=did, render_kind="DRAFT", values=VALUES)
        self.assertEqual(self.scalar("select count(*) from stored_object where object_key like %s", f"renders/{did}/%"), 0)

    def test_audit_chi_mang_ma_va_tham_chieu(self):
        did = self.make_document(self.make_template())
        r = self.render_docx(did)
        self.render_docx(did)
        rows = self.rows("select actor_kind, severity, payload from audit_event where document_id = %s and action = 'document.docx_render' order by occurred_at", did)
        self.assertEqual([x[0] for x in rows], ["SYSTEM", "SYSTEM"])
        self.assertEqual([x[2]["reused"] for x in rows], [False, True])
        blob = json.dumps(rows[0][2], ensure_ascii=False)
        self.assertEqual((rows[0][2]["render_kind"], rows[0][2]["input_hash"]), ("DRAFT", r.input_hash.hex()))
        for v in VALUES.values():
            self.assertNotIn(v, blob)

    def test_template_bi_sua_trong_storage_thi_file_unavailable_khong_render_tu_byte_la(self):
        version = self.make_template()
        did = self.make_document(version)
        key = self.scalar("select source_object_key from template_version where id = %s", version)
        self.raw.put_object(Bucket=self.bucket, Key=key, Body=build_template(extra_paragraphs=("byte lạ",)))  # sửa object sau khi commit
        with self.assertRaises(st.FileUnavailable) as cm:
            self.render_docx(did)
        self.assertEqual(cm.exception.reason, "CHECKSUM_MISMATCH")


class PdfExport(RenderBase):
    def export(self, docx: dr.DocxRender, **kw) -> pe.PdfExport:
        return pe.pdf_export(self.pool, self.storage, self.sys, docx, **kw)

    def test_ghi_pdf_va_them_dong_document_render(self):
        did = self.make_document(self.make_template(), revision_round=2)
        docx = self.render_docx(did)
        out = self.export(docx)
        self.assertEqual((out.reused, out.pdf_key), (False, f"renders/{did}/{docx.input_hash.hex()}.pdf"))
        pdf = self.s3_bytes(out.pdf_key)
        self.assertEqual(hashlib.sha256(pdf).digest(), out.pdf_checksum)
        self.assertIn("GIẤY XÁC NHẬN GIẢ", " ".join(pdf_text(pdf).split()))
        row = self.rows("select id, document_id, operating_mode, render_kind, input_hash, template_version_id, revision_round, docx_object_key, pdf_object_key from document_render where document_id = %s", did)
        self.assertEqual(len(row), 1)
        self.assertEqual(row[0][0], out.render_id)
        self.assertEqual((row[0][2], row[0][3], bytes(row[0][4]), row[0][5], row[0][6], row[0][7], row[0][8]),
                         ("NON_PRODUCTION", "DRAFT", docx.input_hash, docx.template_version_id, 2, docx.docx_key, out.pdf_key))

    def test_goi_lai_khong_chuyen_doi_lai_va_tra_dung_dong_cu(self):
        did = self.make_document(self.make_template())
        docx = self.render_docx(did)
        first = self.export(docx)
        with mock.patch.object(convert, "convert_to_pdf", side_effect=AssertionError("không được chuyển đổi lại")):
            second = self.export(docx)
        self.assertEqual((second.render_id, second.pdf_checksum, second.reused), (first.render_id, first.pdf_checksum, True))
        self.assertEqual(self.scalar("select count(*) from document_render where document_id = %s", did), 1)

    def test_font_thieu_bao_truoc_khi_goi_soffice_va_khong_ghi_gi(self):
        did = self.make_document(self.make_template(fonts=("Times New Roman", "Font Khong Co Bo19", "Arial Giả")))
        docx = self.render_docx(did)
        with mock.patch.object(convert, "convert_to_pdf", side_effect=AssertionError("không được gọi soffice")):
            with self.assertRaises(pe.FontMissing) as cm:
                self.export(docx)
        self.assertEqual(cm.exception.families, ("Arial Giả", "Font Khong Co Bo19"))
        self.assertEqual(cm.exception.code, "FONT_MISSING")
        self.assertEqual(self.scalar("select count(*) from document_render where document_id = %s", did), 0)
        self.assertEqual(self.scalar("select count(*) from stored_object where object_key like %s", f"renders/{did}/%.pdf"), 0)

    def test_chuyen_doi_xong_roi_moi_giang_khoa(self):
        """ADR-015: lease của `stored_object` chỉ phủ thời lượng upload — lúc `soffice` chạy, khoá `.pdf` CHƯA có claim."""
        did = self.make_document(self.make_template())
        docx = self.render_docx(did)
        pdf_key = dr.render_key(docx.document_id, docx.input_hash, "pdf")
        seen: list[int] = []
        real = convert.convert_to_pdf

        def spy(data, **kw):
            seen.append(self.scalar("select count(*) from stored_object where object_key = %s", pdf_key))
            return real(data, **kw)
        with mock.patch.object(convert, "convert_to_pdf", spy):
            self.export(docx)
        self.assertEqual(seen, [0])
        self.assertEqual(self.scalar("select count(*) from stored_object_commit where object_key = %s", pdf_key), 1)

    def test_pdf_khong_tat_dinh_byte_lan_hai_khong_toi_object_storage(self):
        """Bộ chuyển đổi trả byte KHÁC mỗi lần (ADR-015: không giả định tất định). Khoá đã commit thì checksum của lần ghi đầu là chuẩn; byte lần hai không tới storage."""
        did = self.make_document(self.make_template())
        docx = self.render_docx(did)
        outputs = [b"%PDF-1.7 lan mot " + b"x" * 300, b"%PDF-1.7 lan hai " + b"y" * 300]
        with mock.patch.object(convert, "convert_to_pdf", side_effect=outputs):
            a = self.export(docx)
            admin_client().delete_object(Bucket=self.bucket, Key="khong-co-gi")  # không đụng object nào
            b = self.export(docx)
        self.assertEqual((a.pdf_checksum, b.pdf_checksum), (hashlib.sha256(outputs[0]).digest(),) * 2)
        self.assertEqual(self.s3_bytes(a.pdf_key), outputs[0])

    def test_hai_worker_cung_input_mot_dong_mot_pdf(self):
        did = self.make_document(self.make_template())
        docx = self.render_docx(did)
        results: list = []
        errors: list = []
        barrier = threading.Barrier(2)

        def go():
            barrier.wait()
            try:
                results.append(self.export(docx))
            except BaseException as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=go) for _ in range(2)]
        [t.start() for t in threads]
        [t.join(300) for t in threads]
        # Một bên có thể gặp claim của bên kia còn hạn (`ClaimHeld`: trả job về hàng đợi) — chấp nhận; không được có lỗi nào khác và không được có hai dòng.
        for e in errors:
            self.assertIsInstance(e, st.ClaimHeld)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(len({r.render_id for r in results}), 1)
        self.assertEqual(len({r.pdf_checksum for r in results}), 1)
        self.assertEqual(self.scalar("select count(*) from document_render where document_id = %s", did), 1)
        self.assertEqual(self.scalar("select count(*) from stored_object_commit where object_key like %s", f"renders/{did}/%.pdf"), 1)

    def test_nhieu_vong_tich_luy_khong_de_len_nhau(self):
        did = self.make_document(self.make_template())
        a = self.export(self.render_docx(did))
        b = self.export(self.render_docx(did, {**VALUES, "noi_dung": "Vòng hai"}))
        self.assertNotEqual((a.render_id, a.pdf_key), (b.render_id, b.pdf_key))
        self.assertEqual(self.scalar("select count(*) from document_render where document_id = %s", did), 2)

    def test_audit_pdf_export_cung_giao_dich_voi_dong_document_render(self):
        did = self.make_document(self.make_template())
        out = self.export(self.render_docx(did))
        rows = self.rows("select payload from audit_event where document_id = %s and action = 'document.pdf_export'", did)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0][0]["render_id"], rows[0][0]["created"]), (str(out.render_id), True))

    def test_chi_tac_nhan_he_thong(self):
        did = self.make_document(self.make_template())
        docx = self.render_docx(did)
        human = ToolContext.create(Actor.employee(uuid.uuid4(), {"document.issue"}))
        with self.assertRaises(SystemActorRequired):
            pe.pdf_export(self.pool, self.storage, human, docx)

    def test_docx_bi_sua_trong_storage_thi_khong_chuyen_doi_byte_la(self):
        did = self.make_document(self.make_template())
        docx = self.render_docx(did)
        self.raw.put_object(Bucket=self.bucket, Key=docx.docx_key, Body=b"byte la")
        with mock.patch.object(convert, "convert_to_pdf", side_effect=AssertionError("không được chuyển đổi byte lạ")):
            with self.assertRaises(st.FileUnavailable):
                self.export(docx)
        self.assertEqual(self.scalar("select count(*) from document_render where document_id = %s", did), 0)


class Fetch(RenderBase):
    def put(self, data: bytes = b"noi dung") -> str:
        key = f"renders/{uuid.uuid4()}/x.docx"
        st.put_once(self.pool, self.storage, object_key=key, purpose="RENDER_DOCX", content_type="application/octet-stream", data=data, lease_s=120)
        return key

    def test_tra_dung_byte_da_commit(self):
        key = self.put(b"abc")
        self.assertEqual(st.fetch(self.pool, self.storage, key, max_bytes=100), b"abc")

    def test_object_bi_sua_la_file_unavailable_checksum(self):
        key = self.put(b"abc")
        self.raw.put_object(Bucket=self.bucket, Key=key, Body=b"abd")
        with self.assertRaises(st.FileUnavailable) as cm:
            st.fetch(self.pool, self.storage, key, max_bytes=100)
        self.assertEqual((cm.exception.code, cm.exception.reason), ("FILE_UNAVAILABLE", "CHECKSUM_MISMATCH"))

    def test_cung_do_dai_khac_noi_dung_va_khac_do_dai_deu_bi_bat(self):
        for body in (b"xyz", b"abcd", b""):
            key = self.put(b"abc")
            self.raw.put_object(Bucket=self.bucket, Key=key, Body=body)
            with self.assertRaises(st.FileUnavailable):
                st.fetch(self.pool, self.storage, key, max_bytes=100)

    def test_object_mat(self):
        key = self.put()
        self.raw.delete_object(Bucket=self.bucket, Key=key)
        with self.assertRaises(st.FileUnavailable) as cm:
            st.fetch(self.pool, self.storage, key, max_bytes=100)
        self.assertEqual(cm.exception.reason, "MISSING")

    def test_qua_tran_kich_thuoc_khong_doc_object(self):
        key = self.put(b"x" * 50)
        with mock.patch.object(self.storage.__class__, "get", side_effect=AssertionError("không được đọc object quá trần")):
            with self.assertRaises(st.FileUnavailable) as cm:
                st.fetch(self.pool, self.storage, key, max_bytes=49)
        self.assertEqual(cm.exception.reason, "TOO_LARGE")
        self.assertEqual(st.fetch(self.pool, self.storage, key, max_bytes=50), b"x" * 50)  # đúng trần thì được

    def test_khoa_chua_commit_hoac_la(self):
        for key in ("khong/co/khoa.docx",):
            with self.assertRaises(st.FileUnavailable) as cm:
                st.fetch(self.pool, self.storage, key, max_bytes=100)
            self.assertEqual(cm.exception.reason, "NOT_COMMITTED")

    def test_storage_khong_voi_toi_duoc(self):
        key = self.put()
        from bo19.object_storage import ObjectStorage, ObjectStorageConfig
        dead = ObjectStorage(ObjectStorageConfig(endpoint_url="http://127.0.0.1:1", bucket=self.bucket, access_key_id="x", secret_access_key="y", timeout_s=2))
        with self.assertRaises(st.FileUnavailable) as cm:
            st.fetch(self.pool, dead, key, max_bytes=100)
        self.assertEqual(cm.exception.reason, "STORAGE_UNAVAILABLE")

    def test_loi_khong_mang_khoa_object_hay_noi_dung(self):
        key = self.put("BÍ-MẬT".encode("utf-8"))
        self.raw.put_object(Bucket=self.bucket, Key=key, Body=b"khac")
        with self.assertRaises(st.FileUnavailable) as cm:
            st.fetch(self.pool, self.storage, key, max_bytes=100)
        self.assertNotIn(key, f"{cm.exception!r} {cm.exception}")
        self.assertNotIn("BÍ-MẬT", f"{cm.exception!r}")


if __name__ == "__main__":
    unittest.main()
