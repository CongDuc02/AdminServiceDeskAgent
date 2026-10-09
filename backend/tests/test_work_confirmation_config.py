"""Cấu hình loại yêu cầu của Sprint 1 — `0011_slot_definition_label.sql` và data migration `0002_work_confirmation_config.sql` trên PostgreSQL thật đã `migrate_main`. B6a.

Điều được chứng minh: slot schema nạp vào DB khớp bảng ở mục 3.2 của `00-domain.md` (đọc lại bảng, không chép tay); mọi `validation_rules` hợp lệ theo từ vựng v1; `example_phrases` không mang nhãn
giả (chúng áp cả lên Render); file data migration không mang `employee` nào; `label_vi` bắt buộc và không rỗng do DB giữ.

Cần BO19_TEST_PG_SUPERUSER_DSN. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_work_confirmation_config -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import re
import unittest
from pathlib import Path

import psycopg

from bo19.domain import slot_rules
from tests import pg_support

ROOT = Path(__file__).resolve().parents[2]
DATA_MIGRATION = ROOT / "backend" / "migrations" / "data" / "0002_work_confirmation_config.sql"
TYPES = {"string": "STRING", "uuid": "STRING", "enum": "ENUM", "date": "DATE", "text": "TEXT", "int": "INT"}


def doc_slots() -> dict[str, dict]:
    """Bảng slot `WORK_CONFIRMATION` ở 00-domain.md (mục 3.2) — trừ `language` `[Could]`."""
    text = (ROOT / "docs" / "design" / "00-domain.md").read_text(encoding="utf-8")
    block = text.split("### 3.2 `WORK_CONFIRMATION`", 1)[1].split("### 3.3", 1)[0]
    out = {}
    for line in block.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        m = re.match(r"^`([a-z_]+)`$", cells[0]) if len(cells) >= 6 else None
        if not m or m.group(1) == "language":
            continue
        required = cells[4]
        out[m.group(1)] = {"source": cells[2].strip("`"), "sensitivity": cells[3].strip("`"), "required": required == "✔",
                           "data_type": TYPES.get(re.match(r"^(\w+)", cells[1]).group(1))}
    return out


@unittest.skipUnless(pg_support.SUPERUSER_DSN, "cần BO19_TEST_PG_SUPERUSER_DSN")
class CauHinhWorkConfirmation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = pg_support.get_db()
        with cls.db.connect("bo19_app") as c:  # đọc bằng đúng role runtime
            cls.types = {r[0]: r for r in c.execute("select code, name_vi, description, support_status, artifact_kind, document_register_id, example_phrases, requires_seal_default, seal_type_default from request_type").fetchall()}
            cur = c.execute("select slot_name, data_type, source, sensitivity, is_required, validation_rules, description, label_vi, display_order from slot_definition where request_type_code = 'WORK_CONFIRMATION' order by display_order")
            names = [d.name for d in cur.description]
            cls.slots = {r[0]: dict(zip(names, r)) for r in cur.fetchall()}

    def test_catalog_sau_loai_chi_mot_loai_duoc_ho_tro(self):
        self.assertEqual(set(self.types), {"WORK_CONFIRMATION", "INTRODUCTION_LETTER", "ROOM_BOOKING", "SEAL_REQUEST", "INCOME_CONFIRMATION", "BUSINESS_TRIP_ORDER"})
        self.assertEqual({c for c, r in self.types.items() if r[3] == "SUPPORTED"}, {"WORK_CONFIRMATION"})
        wc = self.types["WORK_CONFIRMATION"]
        self.assertEqual((wc[4], wc[7], wc[8]), ("DOCUMENT", True, "ORGANIZATION_ROUND"))
        self.assertIsNotNone(wc[5])  # loại DOCUMENT đang hỗ trợ bắt buộc có sổ

    def test_ten_mo_ta_va_cum_vi_du_khong_rong_va_khong_mang_nhan_gia(self):
        for code, r in self.types.items():
            name, desc, phrases = r[1], r[2], r[6]
            self.assertTrue(name.strip() and desc.strip(), code)
            self.assertGreaterEqual(len(phrases), 3, code)
            for text in (name, desc, *phrases):
                self.assertNotRegex(text, r"\(giả\)|\bgiả\b|\bTEST\b|lorem", code)  # áp cả lên Render: không nhãn giả
                self.assertEqual(text, text.strip(), code)
            self.assertEqual(len(set(phrases)), len(phrases), code)

    def test_cum_vi_du_cua_cac_loai_khong_trung_nhau(self):  # P1 phân loại bằng ví dụ: hai loại chung một cụm là nhập nhằng sẵn
        seen: dict[str, str] = {}
        for code, r in self.types.items():
            for p in r[6]:
                self.assertNotIn(p, seen, f"{p!r}: {seen.get(p)} và {code}")
                seen[p] = code

    def test_slot_khop_bang_00_domain_muc_3_2(self):
        doc = doc_slots()
        self.assertEqual(set(self.slots), set(doc))  # không thừa, không thiếu, và không có `language` [Could]
        for name, d in doc.items():
            db = self.slots[name]
            # Slot SYSTEM "✔ khi ISSUED" ở bảng là is_required = false ở DB (hàm đủ điều kiện chạy trước SUBMITTED); các slot khác khớp nguyên.
            self.assertEqual((db["source"], db["sensitivity"], db["data_type"]), (d["source"], d["sensitivity"], d["data_type"]), name)
            self.assertEqual(db["is_required"], d["required"], name)

    def test_moi_validation_rules_hop_le_theo_tu_vung_v1(self):
        for name, s in self.slots.items():
            self.assertEqual(slot_rules.validate_config(s["data_type"], s["validation_rules"]), [], name)

    def test_rule_dung_nhu_da_duyet(self):
        want = {"purpose": {"non_blank": True, "min_tokens": 3}, "recipient_org": {"non_blank": True}, "copies_count": {"int_range": {"min": 1}},
                "contract_type": {"one_of": ["PROBATION", "FIXED_TERM", "INDEFINITE"]}}
        for name, s in self.slots.items():
            self.assertEqual(s["validation_rules"], want.get(name, {}), name)
        self.assertNotIn("max", self.slots["copies_count"]["validation_rules"]["int_range"])  # A-011 chưa có trần

    def test_contract_type_khop_check_cua_ddl(self):
        with self.db.connect("bo19_migrator") as c:
            definition = c.execute("select pg_get_constraintdef(oid) from pg_constraint where conname = 'ck_employee_contract_type'").fetchone()[0]
        self.assertEqual(set(re.findall(r"'([A-Z_]+)'", definition)), set(self.slots["contract_type"]["validation_rules"]["one_of"]))

    def test_nguon_user_input_dung_ba_slot_va_co_mo_ta_cho_p2(self):
        user = {n for n, s in self.slots.items() if s["source"] == "USER_INPUT"}
        self.assertEqual(user, {"purpose", "recipient_org", "copies_count"})
        for n in user:
            self.assertGreaterEqual(len(self.slots[n]["description"]), 20, n)

    def test_nhan_vi_khong_rong_khong_trung_va_la_chu_khong_phai_ma(self):
        labels = [s["label_vi"] for s in self.slots.values()]
        self.assertEqual(len(set(labels)), len(labels))
        for name, s in self.slots.items():
            self.assertTrue(s["label_vi"].strip(), name)
            self.assertNotEqual(s["label_vi"], name)
            self.assertNotRegex(s["label_vi"], r"^[a-z_]+$", name)

    def test_thu_tu_hien_thi_duy_nhat_va_tang(self):
        orders = [s["display_order"] for s in self.slots.values()]
        self.assertEqual(orders, sorted(set(orders)))

    def test_db_giu_nhan_bat_buoc_va_khong_rong(self):
        with self.db.connect("bo19_migrator") as c:
            base = ("insert into slot_definition (request_type_code, slot_name, data_type, source, sensitivity, is_required, description{cols}) "
                    "values ('WORK_CONFIRMATION', %s, 'STRING', 'USER_INPUT', 'INT', false, 'x'{vals})")
            with self.assertRaises(psycopg.errors.NotNullViolation):
                c.execute(base.format(cols="", vals=""), ("thieu_nhan",))
            c.rollback()
            for blank in ("", "   "):
                with self.assertRaises(psycopg.errors.CheckViolation) as cm:
                    c.execute(base.format(cols=", label_vi", vals=", %s"), ("nhan_rong", blank))
                c.rollback()
                self.assertIn("ck_slot_definition_label_not_blank", str(cm.exception))

    def test_data_migration_chi_la_cau_hinh_khong_co_employee_hay_quyen(self):
        sql = DATA_MIGRATION.read_text(encoding="utf-8")
        code = "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("--"))
        self.assertRegex(code, r"INSERT INTO request_type")
        self.assertEqual(sorted(set(re.findall(r"INSERT\s+INTO\s+(\w+)", code))), ["document_register", "request_type", "slot_definition"])  # đúng ba bảng cấu hình
        for forbidden in (r"GRANT", r"CREATE", r"DROP", r"DELETE", r"UPDATE", r"ALTER"):
            self.assertNotRegex(code, forbidden)

    def test_so_van_ban_cua_loai_duoc_ho_tro_hoat_dong(self):
        with self.db.connect("bo19_app") as c:
            row = c.execute("select r.code, r.reset_policy, r.is_active from document_register r join request_type t on t.document_register_id = r.id where t.code = 'WORK_CONFIRMATION'").fetchone()
        self.assertEqual(row, ("WORK_CONFIRMATION", "YEARLY", True))


if __name__ == "__main__":
    unittest.main()
