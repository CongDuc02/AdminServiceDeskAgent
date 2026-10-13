"""Nhóm endpoint Request (B7) — `GET /requests?scope=OWN`, `GET /requests/{id}`, `POST …/confirm-slots`, `POST …/submit` qua ASGI app thật, PostgreSQL thật, role `bo19_app`.

Điều được chứng minh, nói bằng hành vi:
- chỉ người tạo thấy hay ghi được: yêu cầu của người khác và yêu cầu không tồn tại trả cùng `NOT_FOUND`, thân giống nhau trừ `trace_id`;
- `RequestDetail` tính `missing_slots`, `unconfirmed_slots`, `submit_ready` bằng đúng hàm kiểm F1; mỗi slot có `label`, `sensitivity`, `provenance` với nguồn `HR_PROFILE`;
- `confirm-slots` đích danh từng slot với `expected_row_version`; mã lỗi nội bộ được dịch đúng mục 4.2 của 05-api.md, `details` chỉ mang tên;
- `submit`: AC-1.4 qua HTTP; client không gửi được `submit_ready`; khoá idempotency đúng mục 1.8; lỗi không mang giá trị slot;
- danh sách `OWN` phân trang keyset, cursor gắn bộ lọc; `ALL`/`ASSIGNED` chưa dựng (Sprint 3).

Cần BO19_TEST_PG_SUPERUSER_DSN. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_requests_api -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import unittest
import uuid
from pathlib import Path

import yaml

from bo19.api.schemas import requests as schemas
from bo19.tool_layer.kernel.permission import employee_context
from tests.auth_support import CSRF, AuthBase
from tests.request_support import HR_REQUIRED, PURPOSE, RECIPIENT, build_request, slot_versions
from tests.tool_support import RES

API = "/api/v1"
OPENAPI = Path(__file__).resolve().parents[2] / "docs" / "design" / "contracts" / "openapi.yaml"


class RequestApiBase(AuthBase):
    def setUp(self):
        super().setUp()
        self.eid, self.code = self.employee()
        self.h = self.as_user(self.eid)

    def ctx_of(self, eid):
        with self.pool.acquire() as conn:
            return employee_context(conn, eid)

    def build(self, eid=None, **kw) -> uuid.UUID:
        eid = eid or self.eid
        return build_request(self.pool, self.db, eid, self.ctx_of(eid), **kw)

    def detail(self, rid, headers=None):
        return self.client.get(f"{API}/requests/{rid}", headers=headers or self.h)

    def confirm(self, rid, items, headers=None):
        return self.client.post(f"{API}/requests/{rid}/actions/confirm-slots", json={"confirmations": items}, headers={**CSRF, **(headers or self.h)})

    def submit(self, rid, version, key=None, headers=None, body=None):
        hdr = {**CSRF, **(headers or self.h)}
        if key is not False:
            hdr["Idempotency-Key"] = str(key or uuid.uuid4())
        return self.client.post(f"{API}/requests/{rid}/actions/submit", json=body if body is not None else {"expected_row_version": version}, headers=hdr)

    def counts(self, rid) -> tuple[int, int]:
        with self.db.connect("bo19_migrator") as c:
            d = c.execute("select count(*) from decision_record where request_id = %s", (rid,)).fetchone()[0]
            j = c.execute("select count(*) from job where payload->>'request_id' = %s", (str(rid),)).fetchone()[0]
        return d, j


class ChiTiet(RequestApiBase):
    def test_nguoi_tao_thay_slot_nhan_do_nhay_nguon_va_ket_qua_ham_kiem(self):
        rid = self.build(leave_unconfirmed=("full_name",))
        r = self.detail(rid)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual((body["id"], body["status"], body["status_label"], body["request_type_code"]), (str(rid), "DRAFT", "Đang soạn", "WORK_CONFIRMATION"))
        self.assertEqual(body["beneficiary"]["id"], str(self.eid))
        slots = {s["slot_name"]: s for s in body["slots"]}
        self.assertEqual(slots["full_name"]["label"], "Họ và tên")
        self.assertEqual((slots["full_name"]["value_status"], slots["full_name"]["sensitivity"], slots["full_name"]["source"]), ("PROPOSED", "PER", "HR_PROFILE"))
        self.assertEqual(slots["full_name"]["provenance"]["source"], "TEST_FAKE")
        self.assertIsNotNone(slots["full_name"]["row_version"])
        self.assertEqual((slots["purpose"]["value"], slots["purpose"]["sensitivity"], slots["purpose"]["provenance"]), (PURPOSE, "RES", None))
        self.assertEqual((slots["national_id"]["value_status"], slots["national_id"]["value"], slots["national_id"]["row_version"]), (None, None, None))  # chưa có dòng
        self.assertEqual(body["unconfirmed_slots"], ["full_name"])
        self.assertEqual((body["missing_slots"], body["failed_rules"], body["submit_ready"]), ([], [], False))
        self.assertEqual((body["documents"], body["changes_requested"], body["artifacts"]), ([], None, []))
        self.assertTrue(set(slots) >= set(HR_REQUIRED) | {"purpose", "recipient_org", "copies_count"})

    def test_du_dieu_kien_thi_submit_ready(self):
        rid = self.build()
        body = self.detail(rid).json()
        self.assertEqual((body["submit_ready"], body["unconfirmed_slots"], body["missing_slots"]), (True, [], []))

    def test_nguoi_khac_va_khong_ton_tai_cung_not_found(self):
        rid = self.build()
        other, _ = self.employee()
        a = self.assert_envelope(self.detail(rid, self.as_user(other)), "NOT_FOUND", 404)
        b = self.assert_envelope(self.detail(uuid.uuid4(), self.as_user(other)), "NOT_FOUND", 404)
        self.assertEqual({k: v for k, v in a.items() if k != "trace_id"}, {k: v for k, v in b.items() if k != "trace_id"})
        self.assertNotIn(RES, a["message"])

    def test_khong_co_read_own_thi_not_found(self):
        rid = self.build()
        with self.db.connect("bo19_migrator") as c:
            c.execute("delete from employee_role where employee_id = %s", (self.eid,))
        self.assert_envelope(self.detail(rid), "NOT_FOUND", 404)

    def test_chua_dang_nhap_va_id_hong(self):
        self.assert_envelope(self.client.get(f"{API}/requests/{uuid.uuid4()}"), "UNAUTHENTICATED", 401)
        self.assert_envelope(self.client.get(f"{API}/requests/khong-phai-uuid", headers=self.h), "VALIDATION_FAILED", 422)


class XacNhan(RequestApiBase):
    def test_xac_nhan_tung_slot_roi_submit_ready(self):
        rid = self.build(confirm=False)
        v = slot_versions(self.db, rid)
        r = self.confirm(rid, [{"slot_name": n, "expected_row_version": v[n][1]} for n in HR_REQUIRED])
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["submit_ready"])
        self.assertTrue(all(s["value_status"] == "CONFIRMED" and s["confirmed_at"] for s in body["slots"] if s["slot_name"] in HR_REQUIRED))

    def test_gia_tri_doi_tu_luc_hien_thi_la_slot_value_stale(self):
        rid = self.build(confirm=False)
        v = slot_versions(self.db, rid)
        body = self.assert_envelope(self.confirm(rid, [{"slot_name": "job_title", "expected_row_version": v["job_title"][1] + 1}]), "SLOT_VALUE_STALE", 409)
        self.assertEqual(body["details"], {"slot_names": ["job_title"]})
        self.assertEqual(slot_versions(self.db, rid)["job_title"][0], "PROPOSED")

    def test_slot_khong_co_gia_tri_cho_xac_nhan(self):
        rid = self.build(confirm=False)
        for name in ("national_id", "purpose", "khong_co_slot_nay"):
            with self.subTest(slot=name):
                body = self.assert_envelope(self.confirm(rid, [{"slot_name": name, "expected_row_version": 1}]), "SLOT_NOT_PROPOSED", 409)
                self.assertEqual(body["details"], {"slot_names": [name]})

    def test_tat_ca_hoac_khong_gi(self):
        rid = self.build(confirm=False)
        v = slot_versions(self.db, rid)
        self.assert_envelope(self.confirm(rid, [{"slot_name": "job_title", "expected_row_version": v["job_title"][1]},
                                                {"slot_name": "full_name", "expected_row_version": v["full_name"][1] + 5}]), "SLOT_VALUE_STALE", 409)
        self.assertEqual(slot_versions(self.db, rid)["job_title"][0], "PROPOSED")  # mục đúng cũng lăn theo

    def test_needs_info_ve_draft_khi_du_dieu_kien(self):
        rid = self.build(leave_unconfirmed=("job_title",))
        with self.db.connect("bo19_migrator") as c:
            c.execute("update request set status = 'NEEDS_INFO', needs_info_asked_at = now() where id = %s", (rid,))
        v = slot_versions(self.db, rid)
        body = self.confirm(rid, [{"slot_name": "job_title", "expected_row_version": v["job_title"][1]}]).json()
        self.assertEqual((body["status"], body["submit_ready"]), ("DRAFT", True))

    def test_request_da_gui_khong_xac_nhan_duoc(self):
        rid = self.build(leave_unconfirmed=("job_title",))
        with self.db.connect("bo19_migrator") as c:
            c.execute("update request set status = 'SUBMITTED' where id = %s", (rid,))
        body = self.assert_envelope(self.confirm(rid, [{"slot_name": "job_title", "expected_row_version": 1}]), "REQUEST_NOT_EDITABLE", 409)
        self.assertEqual(body["details"], {"current_status": "SUBMITTED"})

    def test_body_sai_va_nguoi_khac(self):
        rid = self.build(confirm=False)
        for bad in ({"confirmations": []}, {"confirmations": [{"slot_name": "job_title"}]}, {"confirmations": [{"slot_name": "Job Title", "expected_row_version": 1}]},
                    {"confirmations": [{"slot_name": "job_title", "expected_row_version": 0}]}, {"confirmations": [{"slot_name": "job_title", "expected_row_version": True}]},
                    {"confirmations": [{"slot_name": "job_title", "expected_row_version": 1}], "all": True}):
            with self.subTest(body=bad):
                self.assert_envelope(self.client.post(f"{API}/requests/{rid}/actions/confirm-slots", json=bad, headers={**CSRF, **self.h}), "VALIDATION_FAILED", 422)
        other, _ = self.employee()
        v = slot_versions(self.db, rid)
        self.assert_envelope(self.confirm(rid, [{"slot_name": "job_title", "expected_row_version": v["job_title"][1]}], self.as_user(other)), "NOT_FOUND", 404)
        self.assertEqual(slot_versions(self.db, rid)["job_title"][0], "PROPOSED")
        self.assert_envelope(self.client.post(f"{API}/requests/{rid}/actions/confirm-slots", json={"confirmations": [{"slot_name": "job_title", "expected_row_version": 1}]},
                                              headers=self.h), "CSRF_HEADER_MISSING", 403)


class Gui(RequestApiBase):
    def version(self, rid) -> int:
        return self.detail(rid).json()["row_version"]

    def test_ac_1_4_qua_http(self):
        for name in HR_REQUIRED:
            with self.subTest(slot=name):
                rid = self.build(leave_unconfirmed=(name,))
                body = self.assert_envelope(self.submit(rid, self.version(rid)), "REQUEST_NOT_READY", 422)
                self.assertEqual(body["details"], {"missing_slots": [], "unconfirmed_slots": [name], "failed_rules": []})
                self.assertEqual(self.counts(rid), (0, 0))
                self.assertEqual(self.detail(rid).json()["status"], "DRAFT")

    def test_gui_thanh_cong_tra_decision_result(self):
        rid = self.build()
        key = uuid.uuid4()
        r = self.submit(rid, self.version(rid), key)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn("Idempotent-Replayed", r.headers)
        body = r.json()
        self.assertEqual((body["decision_record_id"], body["kind"], body["document"]), (str(key), "SUBMITTED", None))
        self.assertEqual((body["request"]["id"], body["request"]["status"], body["request"]["status_label"]), (str(rid), "SUBMITTED", "Đã gửi, chờ tiếp nhận"))
        self.assertIsNotNone(body["request"]["submitted_at"])
        self.assertEqual(self.counts(rid), (1, 1))
        listed = self.client.get(f"{API}/requests", params={"scope": "OWN", "status": "SUBMITTED"}, headers=self.h).json()["items"]
        self.assertEqual([i["id"] for i in listed], [str(rid)])

    def test_gui_lai_cung_khoa_la_lap_lai(self):
        rid = self.build()
        key, version = uuid.uuid4(), self.version(rid)
        first = self.submit(rid, version, key)
        again = self.submit(rid, version, key)
        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(again.headers.get("Idempotent-Replayed"), "true")
        self.assertEqual(again.json()["decision_record_id"], first.json()["decision_record_id"])
        self.assertEqual(self.counts(rid), (1, 1))

    def test_khoa_cua_nguoi_khac_la_conflict_khong_tra_noi_dung(self):
        rid = self.build()
        key = uuid.uuid4()
        self.submit(rid, self.version(rid), key)
        other, _ = self.employee()
        rid2 = self.build(other)
        h2 = self.as_user(other)
        body = self.assert_envelope(self.submit(rid2, self.detail(rid2, h2).json()["row_version"], key, headers=h2), "IDEMPOTENCY_KEY_CONFLICT", 409)
        self.assertNotIn("details", body)
        self.assertNotIn(str(rid), str(body))
        self.assertEqual(self.counts(rid2), (0, 0))

    def test_client_khong_gui_duoc_submit_ready(self):
        rid = self.build(leave_unconfirmed=("full_name",))
        body = self.assert_envelope(self.submit(rid, None, body={"expected_row_version": self.version(rid), "submit_ready": True}), "VALIDATION_FAILED", 422)
        self.assertEqual(body["details"]["fields"], [{"field": "submit_ready", "code": "NOT_ALLOWED"}])
        self.assertEqual(self.counts(rid), (0, 0))

    def test_row_version_lech_va_trang_thai(self):
        rid = self.build()
        body = self.assert_envelope(self.submit(rid, self.version(rid) + 1), "STATE_CONFLICT", 409)
        self.assertEqual(body["details"], {"current_status": "DRAFT"})
        self.submit(rid, self.version(rid))
        body = self.assert_envelope(self.submit(rid, self.version(rid)), "STATE_CONFLICT", 409)
        self.assertEqual(body["details"], {"current_status": "SUBMITTED"})
        self.assertEqual(self.counts(rid), (1, 1))

    def test_khoa_body_va_quyen(self):
        rid = self.build()
        v = self.version(rid)
        self.assert_envelope(self.submit(rid, v, key=False), "IDEMPOTENCY_KEY_REQUIRED", 400)
        self.assert_envelope(self.submit(rid, v, key="khong-phai-uuid"), "VALIDATION_FAILED", 422)
        for bad in ({}, {"expected_row_version": 0}, {"expected_row_version": "1"}):
            with self.subTest(body=bad):
                self.assert_envelope(self.submit(rid, None, body=bad), "VALIDATION_FAILED", 422)
        other, _ = self.employee()
        self.assert_envelope(self.submit(rid, v, headers=self.as_user(other)), "NOT_FOUND", 404)
        self.assertEqual(self.counts(rid), (0, 0))

    def test_loi_va_ket_qua_khong_mang_gia_tri_slot(self):
        rid = self.build(leave_unconfirmed=("full_name",))
        texts = [self.submit(rid, self.version(rid)).text]
        self.build_ok = self.build()
        texts.append(self.submit(self.build_ok, self.version(self.build_ok)).text)
        for t in texts:
            self.assertNotIn(RES, t)
            self.assertNotIn(RECIPIENT, t)
        self.assertNotIn(RES, self.out.getvalue())  # log kỹ thuật của các request trên


class DanhSach(RequestApiBase):
    def test_chi_cua_minh_moi_nhat_truoc_va_phan_trang(self):
        mine = [self.build() for _ in range(3)]
        other, _ = self.employee()
        self.build(other)
        p1 = self.client.get(f"{API}/requests", params={"scope": "OWN", "limit": 2}, headers=self.h)
        self.assertEqual(p1.status_code, 200, p1.text)
        page1 = p1.json()
        self.assertEqual([i["id"] for i in page1["items"]], [str(r) for r in reversed(mine)][:2])
        self.assertIsNotNone(page1["next_cursor"])
        page2 = self.client.get(f"{API}/requests", params={"scope": "OWN", "limit": 2, "cursor": page1["next_cursor"]}, headers=self.h).json()
        self.assertEqual([i["id"] for i in page2["items"]], [str(mine[0])])
        self.assertIsNone(page2["next_cursor"])
        item = page1["items"][0]
        self.assertEqual((item["status_label"], item["artifacts"], item["beneficiary"]["id"]), ("Đang soạn", [], str(self.eid)))

    def test_cursor_gan_bo_loc(self):
        for _ in range(2):
            self.build()
        cursor = self.client.get(f"{API}/requests", params={"scope": "OWN", "limit": 1}, headers=self.h).json()["next_cursor"]
        body = self.assert_envelope(self.client.get(f"{API}/requests", params={"scope": "OWN", "status": "DRAFT", "limit": 1, "cursor": cursor}, headers=self.h), "VALIDATION_FAILED", 422)
        self.assertEqual(body["details"]["fields"], [{"field": "cursor", "code": "INVALID_FORMAT"}])
        self.assert_envelope(self.client.get(f"{API}/requests", params={"scope": "OWN", "cursor": "rac"}, headers=self.h), "VALIDATION_FAILED", 422)

    def test_scope_va_status(self):
        for scope in ("ALL", "ASSIGNED"):
            body = self.assert_envelope(self.client.get(f"{API}/requests", params={"scope": scope}, headers=self.h), "VALIDATION_FAILED", 422)
            self.assertEqual(body["details"]["fields"], [{"field": "scope", "code": "NOT_ALLOWED"}])
        body = self.assert_envelope(self.client.get(f"{API}/requests", headers=self.h), "VALIDATION_FAILED", 422)
        self.assertEqual(body["details"]["fields"], [{"field": "scope", "code": "REQUIRED"}])
        self.assert_envelope(self.client.get(f"{API}/requests", params={"scope": "own"}, headers=self.h), "VALIDATION_FAILED", 422)
        self.assert_envelope(self.client.get(f"{API}/requests", params={"scope": "OWN", "status": "KHONG_CO"}, headers=self.h), "VALIDATION_FAILED", 422)
        self.assertEqual(self.client.get(f"{API}/requests", params={"scope": "OWN"}, headers=self.h).json(), {"items": [], "next_cursor": None})

    def test_khong_co_read_own_thi_permission_denied(self):
        with self.db.connect("bo19_migrator") as c:
            c.execute("delete from employee_role where employee_id = %s", (self.eid,))
        body = self.assert_envelope(self.client.get(f"{API}/requests", params={"scope": "OWN"}, headers=self.h), "PERMISSION_DENIED", 403)
        self.assertEqual(body["details"], {"permission": "request.read_own"})


class KhopOpenapi(unittest.TestCase):
    """Trường của model khớp `openapi.yaml` — đổi contract mà quên code (hay ngược lại) thì đỏ."""

    @classmethod
    def setUpClass(cls):
        cls.schemas = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))["components"]["schemas"]

    def fields(self, name: str) -> tuple[set[str], set[str]]:
        """(mọi thuộc tính, thuộc tính bắt buộc) của một schema, gộp `allOf`."""
        spec = self.schemas[name]
        props, required = set(spec.get("properties", {})), set(spec.get("required", []))
        for part in spec.get("allOf", []):
            sub_props, sub_req = self.fields(part["$ref"].rsplit("/", 1)[1]) if "$ref" in part else (set(part.get("properties", {})), set(part.get("required", [])))
            props |= sub_props
            required |= sub_req
        return props, required

    def test_model_khop_schema(self):
        for model, name in ((schemas.RequestSummaryOut, "RequestSummary"), (schemas.RequestDetailOut, "RequestDetail"), (schemas.SlotViewOut, "SlotView"),
                            (schemas.DecisionResultOut, "DecisionResult"), (schemas.SlotConfirmBody, "SlotConfirmBody"), (schemas.SubmitBody, "SubmitBody"),
                            (schemas.EmployeeBriefOut, "EmployeeBrief"), (schemas.FailedRuleOut, "FailedRule"), (schemas.ProvenanceOut, "Provenance")):
            with self.subTest(schema=name):
                props, required = self.fields(name)
                self.assertEqual(set(model.model_fields), props)
                self.assertTrue(required <= props)

    def test_slot_view_co_label_bat_buoc(self):
        props, required = self.fields("SlotView")
        self.assertIn("label", required)


if __name__ == "__main__":
    unittest.main()
