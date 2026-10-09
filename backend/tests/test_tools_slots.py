"""`request_slots_write`, `request_slots_propose`, `prior_attempt_lookup`, `employee_lookup`, `request_slot_confirm` và hàm F1 qua `tool_layer.checks` — trên PostgreSQL thật. B6a.

Điều được chứng minh, nói bằng hành vi:
- không giá trị nào vào `request_slot` mà không có bằng chứng nguyên văn (kể cả giá trị bịa đi kèm một đoạn trích thật); bằng chứng phải là tin của chính nhân viên trong phiên;
- `request_slots_propose` chỉ đọc hồ sơ của CHÍNH người yêu cầu và chỉ `EXPIRED` của chính họ — `request` lập hộ người khác bị từ chối (EC-IL-01); không đè `PROVIDED`/`CONFIRMED`;
- `employee_lookup` kiểm quyền TRƯỚC khi đọc hồ sơ người thứ ba và không cho biết người đó có tồn tại hay không;
- xác nhận gắn với `row_version` đã nhìn thấy, tất cả hoặc không gì; `NEEDS_INFO → DRAFT` khi đủ điều kiện;
- `audit_event` và kết quả trả về chỉ mang tên slot và mã — không giá trị (một giá trị `RES` đánh dấu không được xuất hiện ở đâu ngoài `request_slot`).

Cần BO19_TEST_PG_SUPERUSER_DSN. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_tools_slots -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import datetime as dt
import json
import unicodedata
import unittest
import uuid

from psycopg.types.json import Jsonb

from bo19.domain import eligibility as el
from bo19.tool_layer.checks.eligibility import check_request
from bo19.tool_layer.employee_ops.request_slot_confirm import Confirmation, NotProposed, StaleValue, request_slot_confirm
from bo19.tool_layer.endpoint_ops.chat import chat_message_append
from bo19.tool_layer.kernel.permission import PermissionDenied
from bo19.tool_layer.tools._common import NotEditable, NotOwnRequest
from bo19.tool_layer.tools.employee_lookup import FieldNotAllowed, Forbidden, NotFound, employee_lookup
from bo19.tool_layer.tools.prior_attempt_lookup import BeneficiaryNotSelf, prior_attempt_lookup
from bo19.tool_layer.tools.request_open import request_open
from bo19.tool_layer.tools.request_slots_propose import ProposeResult, UnknownOrigin, request_slots_propose
from bo19.tool_layer.tools.request_slots_write import QUOTE_NOT_IN_MESSAGE, VALUE_NOT_IN_QUOTE, SlotWrite, request_slots_write
from bo19.tool_layer.tools.request_transition import request_transition
from tests.tool_support import RES, ToolBase

TEXT = "gửi tới Ngân hàng ABC, mục đích bổ sung hồ sơ vay vốn, cần 2 bản"
HR_REQUIRED = {"full_name", "department_name", "job_title", "contract_type", "employment_start_date"}


class Scenario(ToolBase):
    """Một nhân viên, một phiên, một `request` ở `DRAFT`, và một tin nhắn mang nội dung để làm bằng chứng."""

    def setUp(self):
        super().setUp()
        self.eid, self.ctx_ = self.employee()
        self.sid, _, self.rid, _ = self.open_request(self.eid, self.ctx_)
        self.mid = self.msg(TEXT)

    def msg(self, text: str, *, ctx=None, sid=None) -> uuid.UUID:
        mid = uuid.uuid4()
        chat_message_append(self.pool, ctx or self.ctx_, chat_session_id=sid or self.sid, message_id=mid, author="EMPLOYEE", body=text)
        return mid

    def write(self, items, *, ctx=None, rid=None):
        return request_slots_write(self.pool, ctx or self.ctx_, request_id=rid or self.rid, items=items)

    def item(self, name, value, quote, mid=None, span=None) -> SlotWrite:
        return SlotWrite(name, value, mid or self.mid, quote, span)

    def propose(self, origin="HR_PROFILE", *, ctx=None, rid=None) -> ProposeResult:
        return request_slots_propose(self.pool, ctx or self.ctx_, request_id=rid or self.rid, origin=origin)

    def employee_row(self, employee_id=None) -> dict:
        with self.db.connect("bo19_migrator") as c:
            cur = c.execute("select employee_code, full_name, source, synced_at from employee where id = %s", (employee_id or self.eid,))
            return dict(zip([d.name for d in cur.description], cur.fetchone()))

    def audit_dump(self) -> str:
        return json.dumps([e["payload"] for e in self.audit(self.rid)], ensure_ascii=False, default=str)


class GhiSlot(Scenario):
    def test_ghi_dung_gia_tri_bang_chung_va_vi_tri(self):
        r = self.write([self.item("recipient_org", "Ngân hàng ABC", "Ngân hàng ABC"), self.item("purpose", "bổ sung hồ sơ vay vốn", "bổ sung hồ sơ vay vốn"), self.item("copies_count", 2, "2 bản")])
        self.assertEqual((set(r.written), r.unchanged, r.rejected), ({"recipient_org", "purpose", "copies_count"}, (), ()))
        slots = self.slot_rows(self.rid)
        body = unicodedata.normalize("NFC", TEXT)
        for name, quote in (("recipient_org", "Ngân hàng ABC"), ("purpose", "bổ sung hồ sơ vay vốn"), ("copies_count", "2 bản")):
            s = slots[name]
            self.assertEqual((s["value_status"], s["evidence_message_id"]), ("PROVIDED", self.mid), name)
            self.assertEqual(body[s["evidence_span"].lower:s["evidence_span"].upper], quote, name)  # vị trí do tool tính, khớp nguyên văn
        self.assertEqual((slots["recipient_org"]["value"], slots["copies_count"]["value"]), ("Ngân hàng ABC", 2))

    def test_chi_so_model_dem_sai_bi_bo_qua_va_tool_tinh_lai(self):
        self.write([self.item("recipient_org", "Ngân hàng ABC", "Ngân hàng ABC", span=(0, 3))])  # chỉ số sai: 'gửi'
        s = self.slot_rows(self.rid)["recipient_org"]["evidence_span"]
        self.assertEqual(TEXT[s.lower:s.upper], "Ngân hàng ABC")
        again = self.msg("gửi Ngân hàng ABC nhé")
        self.write([self.item("recipient_org", "Ngân hàng ABC", "Ngân hàng ABC", mid=again, span=(100, 120))])  # tin mới, chỉ số vượt độ dài
        s = self.slot_rows(self.rid)["recipient_org"]["evidence_span"]
        self.assertEqual("gửi Ngân hàng ABC nhé"[s.lower:s.upper], "Ngân hàng ABC")

    def test_nfd_cua_model_khop_voi_body_nfc(self):
        quote = unicodedata.normalize("NFD", "Ngân hàng ABC")
        self.assertNotEqual(quote, "Ngân hàng ABC")
        r = self.write([self.item("recipient_org", unicodedata.normalize("NFD", "Ngân hàng ABC"), quote)])
        self.assertEqual(r.written, ("recipient_org",))
        self.assertEqual(self.slot_rows(self.rid)["recipient_org"]["value"], "Ngân hàng ABC")  # giá trị lưu dạng NFC

    def test_suy_dien_bi_loai_khong_ghi_gi(self):
        other_mid = self.say_in_other_session()
        agent = uuid.uuid4()
        chat_message_append(self.pool, self.sys, chat_session_id=self.sid, message_id=agent, author="AGENT", body="Ngân hàng ABC", reply_template_id="ASK_SLOT")
        cases = {
            "đoạn trích không có trong tin": self.item("recipient_org", "Công ty XYZ", "Công ty XYZ"),
            "đoạn trích thật nhưng giá trị bịa": self.item("recipient_org", "Ngân hàng XYZ", "Ngân hàng ABC"),
            "đoạn trích rỗng": self.item("recipient_org", "Ngân hàng ABC", ""),
            "đoạn trích quá 300 ký tự": self.item("purpose", "x " * 160, "x " * 160),
            "tin của phiên khác": self.item("recipient_org", "Ngân hàng ABC", "Ngân hàng ABC", mid=other_mid),
            "tin của agent": self.item("recipient_org", "Ngân hàng ABC", "Ngân hàng ABC", mid=agent),
            "tin không tồn tại": self.item("recipient_org", "Ngân hàng ABC", "Ngân hàng ABC", mid=uuid.uuid4()),
            "khác hoa thường": self.item("recipient_org", "ngân hàng abc", "ngân hàng abc"),
        }
        for label, it in cases.items():
            r = self.write([it])
            self.assertEqual([(x.slot_name, x.code) for x in r.rejected], [(it.slot_name, "EVIDENCE_MISMATCH")], label)
            self.assertEqual([x.reason for x in r.rejected], [QUOTE_NOT_IN_MESSAGE if label != "đoạn trích thật nhưng giá trị bịa" else VALUE_NOT_IN_QUOTE], label)
            self.assertEqual(r.written, (), label)
        self.assertEqual(set(self.slot_rows(self.rid)), {"requester_employee_code", "beneficiary_employee_id"})  # chỉ còn hai slot hệ thống
        self.assertEqual([e["action"] for e in self.audit(self.rid)], ["request.open"])  # không có gì được ghi → không audit

    def test_value_khop_noi_theo_nfc_casefold_va_gop_khoang_trang_con_quote_van_chinh_xac(self):  # PO, B6b: hai phép khác độ chặt
        mid = self.msg("gửi tới ngân hàng  vietcombank,	mục đích   bổ sung hồ sơ")
        r = self.write([self.item("recipient_org", "Ngân hàng Vietcombank", "ngân hàng  vietcombank", mid=mid)])  # model viết hoa lại, gộp khoảng trắng
        self.assertEqual((r.written, r.rejected), (("recipient_org",), ()))
        self.assertEqual(self.slot_rows(self.rid)["recipient_org"]["value"], "Ngân hàng Vietcombank")  # giá trị lưu là value của model, không phải đoạn trích
        r = self.write([self.item("purpose", "bổ sung hồ sơ", "mục đích   bổ sung hồ sơ", mid=mid), self.item("recipient_org", "ĐẠI HỌC", "đại học", mid=self.msg("gửi tới đại học x"))])
        self.assertEqual((set(r.written), r.rejected), ({"purpose", "recipient_org"}, ()))  # gộp khoảng trắng nhiều loại (cả tab); Đ ↔ đ
        nfd = unicodedata.normalize("NFD", "NGÂN HÀNG VIETCOMBANK")
        self.assertNotEqual(nfd, unicodedata.normalize("NFC", nfd))
        self.assertEqual(self.write([self.item("recipient_org", nfd, "ngân hàng  vietcombank", mid=mid)]).written, ("recipient_org",))  # NFD + hoa: vẫn khớp

    def test_value_bia_hoac_dai_hon_doan_trich_van_la_evidence_mismatch_voi_ma_con(self):
        mid = self.msg("gửi tới ngân hàng  vietcombank, mục đích bổ sung hồ sơ")
        cases = {
            "giá trị bịa": self.item("recipient_org", "Ngân hàng Techcombank", "ngân hàng  vietcombank", mid=mid),
            "dài hơn đoạn trích": self.item("recipient_org", "Ngân hàng Vietcombank chi nhánh 1", "ngân hàng  vietcombank", mid=mid),
            "chỉ khác dấu": self.item("recipient_org", "Ngan hang Vietcombank", "ngân hàng  vietcombank", mid=mid),
            "rỗng": self.item("purpose", "", "mục đích bổ sung hồ sơ", mid=mid),
            "chỉ khoảng trắng": self.item("purpose", " 	 ", "mục đích bổ sung hồ sơ", mid=mid),
        }
        for label, it in cases.items():
            r = self.write([it])
            self.assertEqual([(x.code, x.reason) for x in r.rejected], [("EVIDENCE_MISMATCH", VALUE_NOT_IN_QUOTE)], label)
            self.assertEqual(r.written, (), label)
        self.assertNotIn("recipient_org", self.slot_rows(self.rid))

    def test_quote_van_phai_khop_chinh_xac_voi_tin_nhan_ke_ca_khi_value_khop(self):
        mid = self.msg("gửi tới Ngân hàng ABC")
        for quote in ("ngân hàng abc", "Ngân  hàng ABC", "Ngân hàng ABC "):  # lệch hoa/thường, khoảng trắng, khoảng trắng thừa
            r = self.write([self.item("recipient_org", "Ngân hàng ABC", quote, mid=mid)])
            self.assertEqual([(x.code, x.reason) for x in r.rejected], [("EVIDENCE_MISMATCH", QUOTE_NOT_IN_MESSAGE)], quote)

    def test_audit_chi_mang_ma_ngoai_khong_mang_ma_con_hay_gia_tri(self):
        mid = self.msg("gửi tới ngân hàng  vietcombank")
        self.write([self.item("recipient_org", "ngân hàng vietcombank", "ngân hàng  vietcombank", mid=mid), self.item("purpose", RES, RES, mid=mid)])
        payload = [e for e in self.audit(self.rid) if e["action"] == "request.slots_write"][0]["payload"]
        self.assertEqual(payload["rejected"], ["purpose:EVIDENCE_MISMATCH"])
        self.assertNotIn(RES, self.audit_dump())

    def say_in_other_session(self) -> uuid.UUID:
        eid, ctx = self.employee()
        sid, mid = self.say(eid, ctx, "gửi tới Ngân hàng ABC")
        return mid

    def test_doan_trich_nguyen_van_nhung_qua_300_ky_tu_van_bi_loai(self):  # khớp maxLength của evidence_quote ở schema P2
        long_text = "mục đích " + " ".join(["bổ sung hồ sơ vay vốn"] * 20)
        assert len(long_text) > 300
        mid = self.msg(long_text)
        r = self.write([self.item("purpose", long_text, long_text, mid=mid)])
        self.assertEqual(([x.code for x in r.rejected], r.written), (["EVIDENCE_MISMATCH"], ()))
        ok = self.write([self.item("purpose", long_text[:300], long_text[:300], mid=mid)])  # đúng 300 thì qua
        self.assertEqual(ok.written, ("purpose",))

    def test_rule_hong_bi_loai_kem_ma_rule_khong_kem_gia_tri(self):
        mid = self.msg("mục đích cần gấp, lấy 0 bản, bản 2,5")
        r = self.write([self.item("purpose", "cần gấp", "cần gấp", mid=mid), self.item("copies_count", 0, "0 bản", mid=mid), self.item("copies_count", "2", "2,5", mid=mid)])
        self.assertEqual([(x.slot_name, x.code, x.rule_codes) for x in r.rejected],
                         [("purpose", "RULE_FAILED", ("RULE_MIN_TOKENS",)), ("copies_count", "RULE_FAILED", ("RULE_INT_RANGE",)), ("copies_count", "RULE_FAILED", ("RULE_TYPE",))])
        self.assertEqual(r.written, ())

    def test_slot_khong_duoc_phep(self):
        r = self.write([self.item("full_name", "Nguyễn Văn A", "Nguyễn Văn A"), self.item("national_id", "079", "079"), self.item("document_number", "01", "01"),
                        self.item("requester_employee_code", "NV001", "NV001"), self.item("khong_co", "x", "x")])
        self.assertEqual({x.slot_name: x.code for x in r.rejected}, {"full_name": "SLOT_NOT_ALLOWED", "national_id": "SLOT_NOT_ALLOWED", "document_number": "SLOT_NOT_ALLOWED",
                                                                  "requester_employee_code": "SLOT_NOT_ALLOWED", "khong_co": "SLOT_NOT_ALLOWED"})

    def test_mot_phan_qua_mot_phan_loai_mot_audit(self):
        r = self.write([self.item("recipient_org", "Ngân hàng ABC", "Ngân hàng ABC"), self.item("purpose", "bịa", "bịa")])
        self.assertEqual((r.written, [x.code for x in r.rejected]), (("recipient_org",), ["EVIDENCE_MISMATCH"]))
        events = [e for e in self.audit(self.rid) if e["action"] == "request.slots_write"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["payload"], {"written": ["recipient_org"], "rejected": ["purpose:EVIDENCE_MISMATCH"]})

    def test_idempotent_theo_tin_nhan_ke_ca_khi_model_doi_gia_tri(self):
        self.write([self.item("recipient_org", "Ngân hàng ABC", "Ngân hàng ABC")])
        before = self.slot_rows(self.rid)["recipient_org"]
        r = self.write([self.item("recipient_org", "Ngân hàng ABC", "Ngân hàng ABC")])
        r2 = self.write([self.item("recipient_org", "ABC", "ABC")])  # lượt chạy lại mà model trích khác đi: vẫn không đổi gì
        self.assertEqual((r.written, r.unchanged, r2.written, r2.unchanged), ((), ("recipient_org",), (), ("recipient_org",)))
        self.assertEqual(self.slot_rows(self.rid)["recipient_org"], before)
        self.assertEqual(len([e for e in self.audit(self.rid) if e["action"] == "request.slots_write"]), 1)

    def test_nhan_vien_noi_lai_o_tin_moi_thay_gia_tri_va_xoa_dau_vet_xac_nhan(self):
        self.write([self.item("recipient_org", "Ngân hàng ABC", "Ngân hàng ABC")])
        with self.db.connect("bo19_migrator") as c:
            c.execute("update request_slot set value_status = 'CONFIRMED', confirmed_at = now(), provenance_source = 'X', provenance_synced_at = now() where request_id = %s and slot_name = 'recipient_org'", (self.rid,))
        before = self.slot_rows(self.rid)["recipient_org"]
        new_mid = self.msg("à nhầm, gửi Công ty Hoa Sen")
        self.write([self.item("recipient_org", "Công ty Hoa Sen", "Công ty Hoa Sen", mid=new_mid)])
        after = self.slot_rows(self.rid)["recipient_org"]
        self.assertEqual((after["value"], after["value_status"], after["evidence_message_id"], after["confirmed_at"], after["provenance_source"], after["row_version"]),
                         ("Công ty Hoa Sen", "PROVIDED", new_mid, None, None, before["row_version"] + 1))

    def test_chi_draft_va_needs_info_sua_duoc(self):
        for status in ("SUBMITTED", "IN_REVIEW", "CHANGES_REQUESTED", "APPROVED", "FULFILLED", "REJECTED", "CANCELLED", "EXPIRED"):
            self.set_status(self.rid, status)
            with self.assertRaises(NotEditable, msg=status):
                self.write([self.item("recipient_org", "Ngân hàng ABC", "Ngân hàng ABC")])
        self.assertNotIn("recipient_org", self.slot_rows(self.rid))
        with self.db.connect("bo19_migrator") as c:  # đưa về NEEDS_INFO hợp lệ
            c.execute("update request set status = 'NEEDS_INFO', needs_info_asked_at = now(), closed_at = NULL where id = %s", (self.rid,))
        self.assertEqual(self.write([self.item("recipient_org", "Ngân hàng ABC", "Ngân hàng ABC")]).written, ("recipient_org",))

    def test_quyen_va_chu_so_huu(self):
        it = [self.item("recipient_org", "Ngân hàng ABC", "Ngân hàng ABC")]
        other, octx = self.employee()
        officer, officer_ctx = self.employee(roles=("ADMIN_OFFICER",))  # có request.supply_info nhưng không phải người tạo
        for who in (octx, officer_ctx):
            with self.assertRaises(NotOwnRequest):
                self.write(it, ctx=who)
        with self.assertRaises(NotOwnRequest):
            self.write(it, rid=uuid.uuid4())
        _, noperm = self.employee(roles=())
        with self.assertRaises(PermissionDenied):
            self.write(it, ctx=noperm)
        with self.assertRaises(PermissionDenied):
            self.write(it, ctx=self.sys)
        self.assertNotIn("recipient_org", self.slot_rows(self.rid))

    def test_gia_tri_res_khong_lot_ra_audit_ket_qua_hay_loi(self):
        value = f"{RES} dùng cho hồ sơ"
        mid = self.msg(f"mục đích {value} nhé")
        r = self.write([self.item("purpose", value, value, mid=mid)])
        self.assertEqual(r.written, ("purpose",))
        self.assertNotIn(RES, repr(r))
        self.assertNotIn(RES, self.audit_dump())
        self.assertEqual(self.slot_rows(self.rid)["purpose"]["value"], value)  # ở đây, và chỉ ở đây
        bad = self.write([self.item("purpose", RES, RES, mid=self.mid)])
        self.assertNotIn(RES, repr(bad))
        self.assertNotIn(RES, self.audit_dump())


class DeXuat(Scenario):
    def test_hr_chi_slot_bat_buoc_voi_nguon_va_thoi_diem_dong_bo(self):
        with self.db.connect("bo19_migrator") as c:  # slot tuỳ chọn có dữ liệu: vẫn không được đề xuất
            c.execute("update employee set employment_end_date = date '2026-01-31', date_of_birth = date '1990-05-05', national_id = '079123456789' where id = %s", (self.eid,))
        r = self.propose()
        self.assertEqual(set(r.written), HR_REQUIRED)
        self.assertEqual(r.skipped, ())
        emp = self.employee_row()
        slots = self.slot_rows(self.rid)
        self.assertEqual(set(slots) - {"requester_employee_code", "beneficiary_employee_id"}, HR_REQUIRED)
        for name in HR_REQUIRED:
            s = slots[name]
            self.assertEqual((s["value_status"], s["provenance_source"], s["provenance_synced_at"], s["confirmed_at"], s["evidence_message_id"], s["proposed_from_request_id"]),
                             ("PROPOSED", emp["source"], emp["synced_at"], None, None, None), name)
        self.assertEqual((slots["full_name"]["value"], slots["contract_type"]["value"], slots["employment_start_date"]["value"]), (emp["full_name"], "INDEFINITE", "2020-01-01"))

    def test_audit_chi_mang_ma_va_ten_slot(self):
        self.propose()
        (event,) = [e for e in self.audit(self.rid) if e["action"] == "request.slots_propose"]
        self.assertEqual(event["payload"]["origin"], "HR_PROFILE")
        self.assertEqual(set(event["payload"]["written"]), HR_REQUIRED)
        emp = self.employee_row()
        self.assertNotIn(emp["full_name"], json.dumps(event["payload"], ensure_ascii=False))
        self.assertNotIn(emp["employee_code"], json.dumps(event["payload"], ensure_ascii=False))

    def test_goi_lai_khong_doi_gi_khi_nguon_khong_doi(self):
        self.propose()
        before = self.slot_rows(self.rid)
        again = self.propose()
        self.assertEqual((again.written, sorted(c for _, c in again.skipped)), ((), ["ALREADY_SET"] * 5))
        self.assertEqual(self.slot_rows(self.rid), before)
        self.assertEqual(len([e for e in self.audit(self.rid) if e["action"] == "request.slots_propose"]), 1)

    def test_ho_so_doi_giua_chung_thi_de_xuat_cap_nhat_nhung_khong_de_gia_tri_da_xac_nhan(self):
        self.propose()
        v1 = self.slot_rows(self.rid)
        request_slot_confirm(self.pool, self.ctx_, request_id=self.rid, items=[Confirmation("job_title", v1["job_title"]["row_version"])])
        with self.db.connect("bo19_migrator") as c:
            c.execute("update employee set full_name = 'Tên Đã Đổi', job_title = 'Chức danh mới' where id = %s", (self.eid,))
        r = self.propose()
        self.assertEqual(r.written, ("full_name",))  # PROPOSED → cập nhật
        self.assertIn(("job_title", "ALREADY_SET"), r.skipped)  # CONFIRMED → giữ nguyên
        s = self.slot_rows(self.rid)
        self.assertEqual((s["full_name"]["value"], s["full_name"]["row_version"]), ("Tên Đã Đổi", v1["full_name"]["row_version"] + 1))
        self.assertEqual((s["job_title"]["value"], s["job_title"]["value_status"]), (v1["job_title"]["value"], "CONFIRMED"))

    def test_khong_de_slot_da_provided(self):
        with self.db.connect("bo19_migrator") as c:  # giả lập một dòng PROVIDED trên slot HR (không đường nào của tool ghi ra)
            c.execute("insert into request_slot (request_id, request_type_code, slot_name, value, value_status, evidence_message_id, evidence_span) values (%s, 'WORK_CONFIRMATION', 'full_name', %s, 'PROVIDED', %s, int4range(0, 3))",
                      (self.rid, Jsonb("Tên tự khai"), self.mid))
        r = self.propose()
        self.assertIn(("full_name", "ALREADY_SET"), r.skipped)
        self.assertEqual(self.slot_rows(self.rid)["full_name"]["value"], "Tên tự khai")

    def test_request_lap_ho_nguoi_khac_bi_tu_choi_va_khong_doc_ho_so_ai(self):  # EC-IL-01
        officer, octx = self.employee(roles=("ADMIN_OFFICER",))
        target, _ = self.employee()
        sid, mid = self.say(officer, octx, "lập giấy giúp đồng nghiệp")
        rid = request_open(self.pool, octx, chat_session_id=sid, request_type="WORK_CONFIRMATION", beneficiary_employee_id=target, opened_by_message_id=mid).request_id
        for origin in ("HR_PROFILE", "PRIOR_ATTEMPT"):
            with self.assertRaises(BeneficiaryNotSelf, msg=origin):
                self.propose(origin, ctx=octx, rid=rid)
        self.assertEqual(set(self.slot_rows(rid)), {"requester_employee_code", "beneficiary_employee_id"})  # không một dòng HR nào được ghi

    def test_khong_the_de_xuat_cho_request_cua_nguoi_khac(self):
        other, octx = self.employee()
        officer, officer_ctx = self.employee(roles=("ADMIN_OFFICER",))
        for who in (octx, officer_ctx):
            with self.assertRaises(NotOwnRequest):
                self.propose(ctx=who)
        with self.assertRaises(NotOwnRequest):
            self.propose(rid=uuid.uuid4())
        self.assertEqual(set(self.slot_rows(self.rid)), {"requester_employee_code", "beneficiary_employee_id"})

    def test_gia_tri_ghi_ra_la_cua_chinh_nguoi_yeu_cau_khong_lan_ho_so_nguoi_khac(self):
        other, _ = self.employee()
        with self.db.connect("bo19_migrator") as c:
            c.execute("update employee set full_name = 'HỒ SƠ NGƯỜI KHÁC', job_title = 'Giám đốc người khác' where id = %s", (other,))
        self.propose()
        s = self.slot_rows(self.rid)
        self.assertEqual(s["full_name"]["value"], self.employee_row()["full_name"])
        self.assertNotIn("người khác", json.dumps({k: v["value"] for k, v in s.items()}, ensure_ascii=False).lower())

    def test_trang_thai_quyen_va_origin(self):
        _, noperm = self.employee(roles=())
        with self.assertRaises(PermissionDenied):
            self.propose(ctx=noperm)
        with self.assertRaises(PermissionDenied):
            self.propose(ctx=self.sys)
        with self.assertRaises(UnknownOrigin):
            self.propose("EMPLOYEE_TABLE")
        for status in ("SUBMITTED", "IN_REVIEW", "CHANGES_REQUESTED", "EXPIRED", "CANCELLED"):
            self.set_status(self.rid, status)
            with self.assertRaises(NotEditable, msg=status):
                self.propose()
        self.assertEqual(set(self.slot_rows(self.rid)), {"requester_employee_code", "beneficiary_employee_id"})

    def test_nguon_prior_attempt_chi_lay_slot_int_per_con_giu_qua_rule_va_khong_de(self):
        expired = self.make_expired(self.eid, {"recipient_org": "Ngân hàng ABC", "copies_count": 3, "purpose": None})  # purpose (RES) đã bị xoá khi hết hạn
        r = self.propose("PRIOR_ATTEMPT")
        self.assertEqual((set(r.written), r.skipped), ({"recipient_org", "copies_count"}, ()))
        s = self.slot_rows(self.rid)
        self.assertEqual((s["recipient_org"]["value"], s["recipient_org"]["value_status"], s["recipient_org"]["proposed_from_request_id"], s["recipient_org"]["provenance_source"]),
                         ("Ngân hàng ABC", "PROPOSED", expired, None))
        self.assertNotIn("purpose", s)
        self.assertEqual(self.propose("PRIOR_ATTEMPT").written, ())  # idempotent

    def test_prior_attempt_bo_qua_gia_tri_khong_con_qua_rule_va_slot_res_con_gia_tri(self):
        self.make_expired(self.eid, {"copies_count": 0, "purpose": "mục đích cũ còn sót lại"}, status="EXPIRED")  # copies_count = 0 không còn qua int_range; purpose là RES dù còn giá trị
        r = self.propose("PRIOR_ATTEMPT")
        self.assertEqual((r.written, r.skipped), ((), ()))  # copies_count = 0 không còn qua rule: bị lọc trước khi tới bước ghi
        self.assertNotIn("copies_count", self.slot_rows(self.rid))
        self.assertNotIn("purpose", self.slot_rows(self.rid))  # RES không bao giờ được đề xuất lại

    def test_hr_gia_tri_khong_con_qua_rule_hien_hanh_thi_khong_de_xuat(self):
        with self.db.connect("bo19_migrator") as c:
            c.execute("update slot_definition set validation_rules = '{\"one_of\": [\"PROBATION\"]}'::jsonb where request_type_code = 'WORK_CONFIRMATION' and slot_name = 'contract_type'")
        try:
            r = self.propose()
        finally:
            with self.db.connect("bo19_migrator") as c:
                c.execute("update slot_definition set validation_rules = '{\"one_of\": [\"PROBATION\", \"FIXED_TERM\", \"INDEFINITE\"]}'::jsonb where request_type_code = 'WORK_CONFIRMATION' and slot_name = 'contract_type'")
        self.assertEqual(r.skipped, (("contract_type", "RULE_NO_LONGER_PASSES"),))
        self.assertEqual(set(r.written), HR_REQUIRED - {"contract_type"})

    def test_prior_attempt_chi_expired_gan_nhat_cua_chinh_nguoi_do(self):
        other, _ = self.employee()
        self.make_expired(other, {"recipient_org": "Của người khác"})
        self.make_expired(self.eid, {"recipient_org": "Đã huỷ"}, status="CANCELLED")
        self.make_expired(self.eid, {"recipient_org": "Đã hoàn tất"}, status="FULFILLED")
        self.make_expired(self.eid, {"recipient_org": "Đã xoá giá trị giữ lại"}, cleared=True)
        self.assertEqual(self.propose("PRIOR_ATTEMPT").written, ())  # không có lần thử hợp lệ nào: danh sách rỗng, không phải lỗi
        newest = self.make_expired(self.eid, {"recipient_org": "Lần hết hạn mới nhất"})
        self.assertEqual(self.propose("PRIOR_ATTEMPT").written, ("recipient_org",))
        self.assertEqual(self.slot_rows(self.rid)["recipient_org"]["proposed_from_request_id"], newest)

    def test_prior_attempt_khong_de_slot_da_co_gia_tri(self):
        self.make_expired(self.eid, {"recipient_org": "Ngân hàng cũ"})
        self.write([self.item("recipient_org", "Ngân hàng ABC", "Ngân hàng ABC")])
        r = self.propose("PRIOR_ATTEMPT")
        self.assertEqual((r.written, r.skipped), ((), (("recipient_org", "ALREADY_SET"),)))
        self.assertEqual(self.slot_rows(self.rid)["recipient_org"]["value"], "Ngân hàng ABC")


class TraCuu(Scenario):
    def test_prior_attempt_lookup_tra_danh_sach_hoac_rong_khong_lo_gia_tri_trong_repr(self):
        self.assertEqual(prior_attempt_lookup(self.pool, self.ctx_, beneficiary_employee_id=self.eid, request_type="WORK_CONFIRMATION"), [])
        expired = self.make_expired(self.eid, {"recipient_org": f"Đơn vị {RES}", "copies_count": 2, "purpose": None})
        got = prior_attempt_lookup(self.pool, self.ctx_, beneficiary_employee_id=self.eid, request_type="WORK_CONFIRMATION")
        self.assertEqual({(p.slot_name, p.source_request_id) for p in got}, {("recipient_org", expired), ("copies_count", expired)})
        self.assertNotIn(RES, repr(got))
        self.assertEqual({p.slot_name: p.value for p in got}["copies_count"], 2)

    def test_chi_tra_cho_chinh_nguoi_thu_huong(self):
        other, octx = self.employee()
        with self.assertRaises(BeneficiaryNotSelf):
            prior_attempt_lookup(self.pool, self.ctx_, beneficiary_employee_id=other, request_type="WORK_CONFIRMATION")
        with self.assertRaises(NotOwnRequest):
            prior_attempt_lookup(self.pool, self.sys, beneficiary_employee_id=self.eid, request_type="WORK_CONFIRMATION")

    def test_tra_cuu_chinh_minh_kem_nguon_va_thoi_diem(self):
        emp = self.employee_row()
        got = employee_lookup(self.pool, self.ctx_, employee_code=emp["employee_code"], request_type="WORK_CONFIRMATION", fields=["full_name", "employment_start_date", "contract_type"])
        self.assertEqual(got.employee_id, self.eid)
        self.assertEqual({k: (v.value, v.source, v.synced_at) for k, v in got.fields.items()},
                         {"full_name": (emp["full_name"], emp["source"], emp["synced_at"]), "employment_start_date": ("2020-01-01", emp["source"], emp["synced_at"]),
                          "contract_type": ("INDEFINITE", emp["source"], emp["synced_at"])})
        self.assertNotIn(emp["full_name"], repr(got))

    def test_chi_kiem_ton_tai_khi_fields_rong(self):
        emp = self.employee_row()
        got = employee_lookup(self.pool, self.ctx_, employee_code=emp["employee_code"], request_type="WORK_CONFIRMATION", fields=[])
        self.assertEqual((got.employee_id, got.fields), (self.eid, {}))

    def test_nguoi_thu_ba_khong_co_quyen_la_forbidden_dong_nhat_ke_ca_khi_khong_ton_tai(self):
        other, _ = self.employee()
        other_code = self.employee_row(other)["employee_code"]
        results = []
        for code in (other_code, "KHONG-TON-TAI-123"):
            with self.assertRaises(Forbidden) as cm:
                employee_lookup(self.pool, self.ctx_, employee_code=code, request_type="WORK_CONFIRMATION", fields=["full_name"])
            results.append((type(cm.exception), str(cm.exception)))
        self.assertEqual(results[0], results[1])  # không cho biết người đó có tồn tại hay không

    def test_forbidden_den_truoc_kiem_truong_va_truoc_khi_doc(self):
        other, _ = self.employee()
        with self.assertRaises(Forbidden):  # trường sai nhưng quyền đến trước
            employee_lookup(self.pool, self.ctx_, employee_code=self.employee_row(other)["employee_code"], request_type="WORK_CONFIRMATION", fields=["password_hash"])

    def test_co_create_on_behalf_tra_cuu_duoc_nguoi_khac(self):
        officer, octx = self.employee(roles=("ADMIN_OFFICER",))
        other, _ = self.employee()
        code = self.employee_row(other)["employee_code"]
        got = employee_lookup(self.pool, octx, employee_code=code, request_type="WORK_CONFIRMATION", fields=["full_name"])
        self.assertEqual(got.employee_id, other)
        with self.assertRaises(NotFound):
            employee_lookup(self.pool, octx, employee_code="KHONG-TON-TAI-123", request_type="WORK_CONFIRMATION", fields=["full_name"])
        inactive, _ = self.db.make_employee(active=False)
        with self.assertRaises(NotFound):
            employee_lookup(self.pool, octx, employee_code=self.employee_row(inactive)["employee_code"], request_type="WORK_CONFIRMATION", fields=[])

    def test_truong_ngoai_slot_schema_la_field_not_allowed(self):
        code = self.employee_row()["employee_code"]
        for fields in (["password_hash"], ["is_active"], ["employee_code"], ["purpose"], ["full_name", "id"], ["full_name; DROP TABLE employee"], ["1"], [""]):
            with self.assertRaises(FieldNotAllowed, msg=fields):
                employee_lookup(self.pool, self.ctx_, employee_code=code, request_type="WORK_CONFIRMATION", fields=fields)
        with self.assertRaises(FieldNotAllowed):  # loại không tồn tại: không có slot HR_PROFILE nào được phép
            employee_lookup(self.pool, self.ctx_, employee_code=code, request_type="LOAI_LA", fields=["full_name"])

    def test_he_thong_khong_tra_cuu_duoc(self):
        with self.assertRaises(NotOwnRequest):
            employee_lookup(self.pool, self.sys, employee_code="x", request_type="WORK_CONFIRMATION", fields=[])


class XacNhan(Scenario):
    def confirm(self, names, *, ctx=None, versions=None, rid=None):
        slots = self.slot_rows(rid or self.rid)
        items = [Confirmation(n, (versions or {}).get(n, slots[n]["row_version"] if n in slots else 1)) for n in names]
        return request_slot_confirm(self.pool, ctx or self.ctx_, request_id=rid or self.rid, items=items)

    def test_xac_nhan_tung_slot(self):
        self.propose()
        before = self.slot_rows(self.rid)["full_name"]
        r = self.confirm(["full_name", "job_title"])
        self.assertEqual((set(r.confirmed), r.unchanged, r.status, r.eligible), ({"full_name", "job_title"}, (), "DRAFT", False))
        s = self.slot_rows(self.rid)
        self.assertEqual((s["full_name"]["value_status"], s["full_name"]["row_version"], s["full_name"]["value"]), ("CONFIRMED", before["row_version"] + 1, before["value"]))
        self.assertIsNotNone(s["full_name"]["confirmed_at"])
        self.assertEqual(s["department_name"]["value_status"], "PROPOSED")  # chỉ slot được chỉ đích danh
        (event,) = [e for e in self.audit(self.rid) if e["action"] == "request.slot_confirm"]
        self.assertEqual((event["payload"]["confirmed"], event["payload"]["status_to"]), (["full_name", "job_title"], "DRAFT"))

    def test_gia_tri_doi_giua_luc_hien_thi_va_luc_bam_thi_xac_nhan_hong(self):
        self.propose()
        seen = self.slot_rows(self.rid)["full_name"]["row_version"]
        with self.db.connect("bo19_migrator") as c:
            c.execute("update employee set full_name = 'Tên Mới' where id = %s", (self.eid,))
        self.propose()  # đề xuất cập nhật → row_version tăng
        with self.assertRaises(StaleValue):
            self.confirm(["full_name"], versions={"full_name": seen})
        self.assertEqual(self.slot_rows(self.rid)["full_name"]["value_status"], "PROPOSED")  # không trượt sang giá trị mới

    def test_tat_ca_hoac_khong_gi(self):
        self.propose()
        s = self.slot_rows(self.rid)
        with self.assertRaises(StaleValue):
            self.confirm(["full_name", "job_title"], versions={"job_title": s["job_title"]["row_version"] + 5})
        after = self.slot_rows(self.rid)
        self.assertEqual((after["full_name"]["value_status"], after["job_title"]["value_status"]), ("PROPOSED", "PROPOSED"))  # mục đầu hợp lệ cũng không được giữ
        self.assertEqual([e["action"] for e in self.audit(self.rid) if e["action"] == "request.slot_confirm"], [])

    def test_khong_phai_proposed_la_not_proposed(self):
        self.write([self.item("recipient_org", "Ngân hàng ABC", "Ngân hàng ABC")])
        for name in ("recipient_org", "khong_co_slot_nay", "requester_employee_code"):  # PROVIDED · không có dòng · SYSTEM_SET
            with self.assertRaises(NotProposed, msg=name):
                self.confirm([name])

    def test_da_xac_nhan_thi_khong_lam_gi_ke_ca_khi_phien_ban_cu(self):
        self.propose()
        self.confirm(["full_name"])
        before = self.slot_rows(self.rid)["full_name"]
        r = self.confirm(["full_name"], versions={"full_name": 1})
        self.assertEqual((r.confirmed, r.unchanged), ((), ("full_name",)))
        self.assertEqual(self.slot_rows(self.rid)["full_name"], before)
        self.assertEqual(len([e for e in self.audit(self.rid) if e["action"] == "request.slot_confirm"]), 1)

    def test_needs_info_ve_draft_khi_du_dieu_kien_va_chi_khi_do(self):
        self.write([self.item("recipient_org", "Ngân hàng ABC", "Ngân hàng ABC"), self.item("purpose", "bổ sung hồ sơ vay vốn", "bổ sung hồ sơ vay vốn")])
        self.propose()
        request_transition(self.pool, self.sys, request_id=self.rid, to="NEEDS_INFO")
        names = sorted(HR_REQUIRED)
        r = self.confirm(names[:-1])
        self.assertEqual((r.status, r.eligible), ("NEEDS_INFO", False))  # còn một mục
        self.assertEqual(self.request_row(self.rid)["status"], "NEEDS_INFO")
        r = self.confirm(names[-1:])
        self.assertEqual((r.status, r.eligible), ("DRAFT", True))
        self.assertEqual(self.request_row(self.rid)["status"], "DRAFT")
        (event,) = [e for e in self.audit(self.rid) if e["action"] == "request.slot_confirm" and e["payload"]["status_to"] == "DRAFT" and names[-1] in e["payload"]["confirmed"]]
        self.assertIsNotNone(event)

    def test_draft_du_dieu_kien_van_o_draft(self):
        self.write([self.item("recipient_org", "Ngân hàng ABC", "Ngân hàng ABC"), self.item("purpose", "bổ sung hồ sơ vay vốn", "bổ sung hồ sơ vay vốn")])
        self.propose()
        r = self.confirm(sorted(HR_REQUIRED))
        self.assertEqual((r.status, r.eligible), ("DRAFT", True))  # không đổi trạng thái khi không ở NEEDS_INFO

    def test_quyen_chu_so_huu_va_trang_thai(self):
        self.propose()
        _, noperm = self.employee(roles=())
        other, octx = self.employee()
        with self.assertRaises(PermissionDenied):
            self.confirm(["full_name"], ctx=noperm)
        with self.assertRaises(PermissionDenied):
            self.confirm(["full_name"], ctx=self.sys)
        with self.assertRaises(NotOwnRequest):
            self.confirm(["full_name"], ctx=octx)
        self.set_status(self.rid, "SUBMITTED")
        with self.assertRaises(NotEditable):
            self.confirm(["full_name"])
        self.assertEqual(self.slot_rows(self.rid)["full_name"]["value_status"], "PROPOSED")


class HamDuDieuKienQuaDb(Scenario):
    def codes(self):
        return {(r.code, r.slot_name) for r in check_request(self.pool_conn, self.rid).reasons}

    def setUp(self):
        super().setUp()
        self._cm = self.pool.acquire()
        self.pool_conn = self._cm.__enter__()
        self.addCleanup(self._cm.__exit__, None, None, None)

    def test_vua_mo_con_thieu_hai_slot_nguoi_dung_va_nam_slot_hr(self):
        self.assertEqual(self.codes(), {(el.SLOT_MISSING, n) for n in HR_REQUIRED | {"purpose", "recipient_org"}})

    def test_day_du_roi_moi_du_dieu_kien(self):
        self.write([self.item("recipient_org", "Ngân hàng ABC", "Ngân hàng ABC"), self.item("purpose", "bổ sung hồ sơ vay vốn", "bổ sung hồ sơ vay vốn")])
        self.assertEqual(self.codes(), {(el.SLOT_MISSING, n) for n in HR_REQUIRED})
        self.propose()
        self.pool_conn.rollback()
        self.assertEqual(self.codes(), {(el.SLOT_UNCONFIRMED, n) for n in HR_REQUIRED})  # AC-1.4: còn HR_PROFILE chưa xác nhận
        self.confirm_all()
        self.pool_conn.rollback()
        check = check_request(self.pool_conn, self.rid)
        self.assertEqual((check.reasons, check.eligible, check.status), ((), True, "DRAFT"))

    def confirm_all(self):
        slots = self.slot_rows(self.rid)
        request_slot_confirm(self.pool, self.ctx_, request_id=self.rid, items=[Confirmation(n, slots[n]["row_version"]) for n in sorted(HR_REQUIRED)])

    def test_lap_ho_khong_co_quyen_la_on_behalf_forbidden(self):
        with self.db.connect("bo19_migrator") as c:
            other, _ = self.db.make_employee()
            c.execute("update request set beneficiary_employee_id = %s where id = %s", (other, self.rid))  # giả lập: người tạo là nhân viên thường, người thụ hưởng khác
        self.pool_conn.rollback()
        self.assertIn((el.ON_BEHALF_FORBIDDEN, None), self.codes())

    def test_request_khong_ton_tai(self):
        from bo19.tool_layer.checks.eligibility import RequestNotFound
        with self.assertRaises(RequestNotFound):
            check_request(self.pool_conn, uuid.uuid4())

    def test_cau_hinh_hien_hanh_duoc_ap_dung_khi_rule_doi(self):
        self.write([self.item("recipient_org", "Ngân hàng ABC", "Ngân hàng ABC"), self.item("purpose", "bổ sung hồ sơ vay vốn", "bổ sung hồ sơ vay vốn")])
        self.propose()
        self.confirm_all()
        self.pool_conn.rollback()
        self.assertTrue(check_request(self.pool_conn, self.rid).eligible)
        with self.db.connect("bo19_migrator") as c:  # siết rule SAU khi đã ghi: request đang dở bị đánh giá theo cấu hình mới (04-data.md)
            c.execute("update slot_definition set validation_rules = '{\"non_blank\": true, \"min_tokens\": 9}'::jsonb where request_type_code = 'WORK_CONFIRMATION' and slot_name = 'purpose'")
        try:
            self.pool_conn.rollback()
            self.assertEqual({(r.code, r.slot_name) for r in check_request(self.pool_conn, self.rid).reasons}, {("RULE_MIN_TOKENS", "purpose")})
        finally:
            with self.db.connect("bo19_migrator") as c:
                c.execute("update slot_definition set validation_rules = '{\"non_blank\": true, \"min_tokens\": 3}'::jsonb where request_type_code = 'WORK_CONFIRMATION' and slot_name = 'purpose'")


if __name__ == "__main__":
    unittest.main()
