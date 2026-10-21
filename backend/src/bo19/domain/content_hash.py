"""`approved_content_hash` — dạng chuẩn tắc của INV-01 (mục 6.4.2 của 03-agents.md; ADR-040 mục 4). Hàm thuần, không IO.

`document_approve_content` ghi hash này lúc duyệt; `finalize_issue` (B9b2) tính lại từ đúng các giá trị dùng cho bản `FINAL` rồi so — lệch một byte là **không phát hành**. Hai nơi gọi **cùng hàm này**, không viết hai lần.

Đầu vào: phiên bản template đã ghim, `operating_mode` đã ghim, và giá trị của mọi biến **không** mang cờ *điền sau duyệt* (số văn bản, ngày ban hành, người ký không vào — INV-01). Đầu ra: SHA-256 (32 byte) của JSON
chuẩn tắc `{"v":1,"template_version_id":…,"operating_mode":…,"values":{…}}` — khoá sắp tăng dần, UTF-8, không khoảng trắng thừa, không escape ký tự không ASCII. Đổi dạng chuẩn tắc là đổi `v`, không sửa tại chỗ.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping

VERSION = 1


def canonical_json(*, template_version_id: uuid.UUID | str, operating_mode: str, values: Mapping[str, str]) -> bytes:
    body = {"v": VERSION, "template_version_id": str(template_version_id), "operating_mode": operating_mode, "values": {k: values[k] for k in sorted(values)}}
    return json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def approved_content_hash(*, template_version_id: uuid.UUID | str, operating_mode: str, values: Mapping[str, str]) -> bytes:
    return hashlib.sha256(canonical_json(template_version_id=template_version_id, operating_mode=operating_mode, values=values)).digest()
