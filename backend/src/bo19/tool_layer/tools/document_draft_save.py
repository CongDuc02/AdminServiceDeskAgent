"""Tool `document_draft_save` — ghi MỖI LẦN sinh một biến nội dung tự do (mục Tool Registry của 03-agents.md; mục `document_free_content` của 04-data.md; ADR-009, ADR-039, A-097).

Một dòng cho mỗi (`document`, biến, vòng, lần sinh); `attempt_no` ∈ {1, 2} — lần sinh chính và lần sinh lại duy nhất. **Ghi một lần**: gọi lại cùng khoá thì không ghi đè (trả `created = False`); văn bản của lần đầu đứng.
**Chặn cứng khi `document` không ở `DRAFT`** (`NOT_DRAFT`) — lớp thứ hai của INV-01: sau cổng 1 không có đường nào ghi nội dung. `validation_outcome` (`PASSED`/`FAILED`) do `validate_free_content` quyết **trước** khi gọi tool này.

**Dấu vân tay input (ADR-009):** hàm băm **có khoá** của input đã dùng (giá trị các slot đã khai cho biến, `variable_guidance`, `request_type`) — băm trần một chuỗi ngắn như `purpose` là đoán ngược được. Khoá: HMAC-SHA256 với **secret riêng** `BO19_RENDER_FINGERPRINT_KEY`
(A-097, PO 2026-10-15 — không dẫn xuất từ secret phiên: đổi secret phiên không được làm đổi dấu vân tay đã lưu, lộ một secret không được là lộ cả hai mục đích), `fingerprint_key_id = "render-fp-v1"`;
bước kiểm khởi động #24 bảo đảm khoá có mặt và dài ≥ 32 byte. Lưu ở bảng nghiệp vụ, không ở state.

`audit_event` `document.draft_save`: tên biến, vòng, lần sinh, kết quả, phiên bản prompt module — **không** văn bản.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from bo19.persistence.pool import Pool
from bo19.persistence.write import unit_of_work
from bo19.tool_layer.kernel import audit
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.kernel.permission import require_system
from bo19.tool_layer.tools._common import ToolError

KEY_ID = "render-fp-v1"
OUTCOMES = ("PASSED", "FAILED")


class NotDraft(ToolError):
    code = "NOT_DRAFT"


class RoundMismatch(ToolError):
    code = "ROUND_MISMATCH"


class DocumentNotFound(ToolError):
    code = "DOCUMENT_NOT_FOUND"


class InputFingerprinter:
    """Băm có khoá của input một lần sinh. Không có khoá trong `repr`."""

    def __init__(self, key: str, *, key_id: str = KEY_ID) -> None:
        if not key:
            raise ValueError("key")
        self._key = key.encode("utf-8")
        self.key_id = key_id

    def __repr__(self) -> str:
        return f"InputFingerprinter(key_id={self.key_id!r})"

    def digest(self, variable_name: str, inputs: Mapping[str, Any]) -> bytes:
        canonical = json.dumps({"variable_name": variable_name, "inputs": dict(sorted(inputs.items()))}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hmac.new(self._key, canonical.encode("utf-8"), hashlib.sha256).digest()


@dataclass(frozen=True)
class DraftSaved:
    created: bool  # False: khoá đã có dòng — văn bản của lần ghi đầu đứng


def document_draft_save(pool: Pool, ctx: ToolContext, *, document_id: uuid.UUID, variable_name: str, revision_round: int, attempt_no: int, body: str, validation_outcome: str,
                        prompt_module_version: str, input_fingerprint: bytes, fingerprint_key_id: str = KEY_ID) -> DraftSaved:
    require_system(ctx)
    if attempt_no not in (1, 2) or validation_outcome not in OUTCOMES or not body:
        raise ValueError("draft_save")
    with pool.acquire() as conn, unit_of_work(conn):
        doc = conn.execute("SELECT status, revision_round, template_version_id, request_id FROM document WHERE id = %s FOR SHARE", (document_id,)).fetchone()
        if doc is None:
            raise DocumentNotFound
        status, current_round, version_id, request_id = doc
        if status != "DRAFT":
            raise NotDraft
        if revision_round != current_round:
            raise RoundMismatch
        row = conn.execute("INSERT INTO document_free_content (id, document_id, variable_name, revision_round, attempt_no, template_version_id, body, validation_outcome, "
                           "prompt_module_version, input_fingerprint, fingerprint_key_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                           "ON CONFLICT (document_id, variable_name, revision_round, attempt_no) DO NOTHING RETURNING id",
                           (uuid.uuid4(), document_id, variable_name, revision_round, attempt_no, version_id, body, validation_outcome, prompt_module_version,
                            input_fingerprint, fingerprint_key_id)).fetchone()
        created = row is not None
        if created:
            audit.record(conn, ctx, action="document.draft_save", entity_type="document", entity_id=document_id, document_id=document_id, request_id=request_id,
                         payload={"variable_name": variable_name, "revision_round": revision_round, "attempt_no": attempt_no, "outcome": validation_outcome,
                                  "prompt_module_version": prompt_module_version})
    return DraftSaved(created)
