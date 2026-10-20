"""`domain.content_hash` — dạng chuẩn tắc của `approved_content_hash` (INV-01; mục 6.4.2 của 03-agents.md; ADR-040 mục 4). Hàm thuần, không DB.

`finalize_issue` (B9b2) gọi lại đúng hàm này: lệch một byte là văn bản không phát hành được, nên test này khoá **từng thành phần của hash** — đổi bất kỳ thành phần nào phải đổi hash, và những gì không được vào hash
(biến điền sau duyệt) không có chỗ để vào.

Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_content_hash -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import hashlib
import unittest
import uuid

from bo19.domain.content_hash import VERSION, approved_content_hash, canonical_json

V = uuid.UUID("11111111-2222-4333-8444-555555555555")
VALUES = {"full_name": "Nguyễn Văn A (GIẢ)", "purpose_statement": "Giấy xác nhận này được cấp để bổ sung hồ sơ.", "recipient_org": "Ngân hàng GIẢ ABC"}


class DangChuanTac(unittest.TestCase):
    def test_json_chuan_tac_dung_tung_byte(self):
        got = canonical_json(template_version_id=V, operating_mode="NON_PRODUCTION", values={"b": "2", "a": "Đ"})
        self.assertEqual(got, '{"operating_mode":"NON_PRODUCTION","template_version_id":"11111111-2222-4333-8444-555555555555","v":1,"values":{"a":"Đ","b":"2"}}'.encode("utf-8"))

    def test_hash_la_sha256_cua_json(self):
        digest = approved_content_hash(template_version_id=V, operating_mode="NON_PRODUCTION", values=VALUES)
        self.assertEqual(digest, hashlib.sha256(canonical_json(template_version_id=V, operating_mode="NON_PRODUCTION", values=VALUES)).digest())
        self.assertEqual(len(digest), 32)

    def test_phien_ban_dinh_dang(self):
        self.assertEqual(VERSION, 1)  # đổi dạng chuẩn tắc là đổi `v`, không sửa tại chỗ
        self.assertIn(b'"v":1', canonical_json(template_version_id=V, operating_mode="NON_PRODUCTION", values={}))

    def test_thu_tu_khoa_khong_anh_huong(self):
        a = approved_content_hash(template_version_id=V, operating_mode="NON_PRODUCTION", values=dict(VALUES))
        b = approved_content_hash(template_version_id=V, operating_mode="NON_PRODUCTION", values=dict(reversed(list(VALUES.items()))))
        self.assertEqual(a, b)

    def test_uuid_va_chuoi_cung_mot_hash(self):
        self.assertEqual(approved_content_hash(template_version_id=V, operating_mode="NON_PRODUCTION", values=VALUES),
                         approved_content_hash(template_version_id=str(V), operating_mode="NON_PRODUCTION", values=VALUES))


class MoiThanhPhanDeuVaoHash(unittest.TestCase):
    base = approved_content_hash(template_version_id=V, operating_mode="NON_PRODUCTION", values=VALUES)

    def test_doi_gia_tri_mot_bien(self):
        for name in VALUES:
            changed = {**VALUES, name: VALUES[name] + " "}
            self.assertNotEqual(approved_content_hash(template_version_id=V, operating_mode="NON_PRODUCTION", values=changed), self.base, name)

    def test_them_hay_bot_mot_bien(self):
        self.assertNotEqual(approved_content_hash(template_version_id=V, operating_mode="NON_PRODUCTION", values={**VALUES, "extra": "x"}), self.base)
        self.assertNotEqual(approved_content_hash(template_version_id=V, operating_mode="NON_PRODUCTION", values={k: v for k, v in VALUES.items() if k != "recipient_org"}), self.base)

    def test_doi_phien_ban_template(self):
        self.assertNotEqual(approved_content_hash(template_version_id=uuid.uuid4(), operating_mode="NON_PRODUCTION", values=VALUES), self.base)

    def test_doi_operating_mode(self):
        self.assertNotEqual(approved_content_hash(template_version_id=V, operating_mode="PRODUCTION", values=VALUES), self.base)

    def test_doi_ten_bien_cung_gia_tri(self):
        renamed = {("recipient_org2" if k == "recipient_org" else k): v for k, v in VALUES.items()}
        self.assertNotEqual(approved_content_hash(template_version_id=V, operating_mode="NON_PRODUCTION", values=renamed), self.base)

    def test_hoan_doi_gia_tri_giua_hai_bien(self):
        swapped = {**VALUES, "full_name": VALUES["recipient_org"], "recipient_org": VALUES["full_name"]}
        self.assertNotEqual(approved_content_hash(template_version_id=V, operating_mode="NON_PRODUCTION", values=swapped), self.base)

    def test_khong_nham_ranh_gioi_giua_khoa_va_gia_tri(self):
        a = approved_content_hash(template_version_id=V, operating_mode="NON_PRODUCTION", values={"ab": "c"})
        b = approved_content_hash(template_version_id=V, operating_mode="NON_PRODUCTION", values={"a": "bc"})
        self.assertNotEqual(a, b)

    def test_unicode_khong_bi_escape_thanh_ascii(self):
        self.assertIn("Đ".encode("utf-8"), canonical_json(template_version_id=V, operating_mode="NON_PRODUCTION", values={"a": "Đ"}))


if __name__ == "__main__":
    unittest.main()
