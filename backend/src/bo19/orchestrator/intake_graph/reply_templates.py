"""Khuôn câu trả lời của `intake_graph` — nạp, kiểm và lắp (`proposals/reply-templates.md`, PO duyệt 2026-10-09; bước kiểm khởi động #23).

`render_reply` là node tất định, không LLM (ADR-007): câu trả lời lắp từ khuôn trong `reply_templates.json`. Tham số có **kiểu đóng** — không có kiểu "chuỗi bất kỳ" — và mọi giá trị đến từ cấu hình DB
(`request_type.name_vi`, `slot_definition.label_vi`) hoặc danh mục trạng thái, **không** từ nhân viên hay từ LLM; nên không thể lọt PII hay chỉ thị vào câu trả lời. Fail-closed: thiếu hay thừa tham số,
khuôn lạ, kiểu sai, danh sách rỗng → `ReplyTemplateError` mang một mã — không bao giờ để lộ lỗi cho nhân viên.
Lắp bằng thay chuỗi `{tên}` từng chỗ, không dùng `str.format` — khuôn không có cú pháp thuộc tính hay chỉ mục; giá trị tham số có chứa `{`, `}` nằm nguyên văn (`str.format` cũng không diễn giải lại giá trị đã thế, nên đây là lựa chọn rõ ràng chứ không phải chỗ khác biệt hành vi).
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
DEFAULT_PATH = Path(__file__).with_name("reply_templates.json")
MAX_TEXT_CHARS = 600
_ID = re.compile(r"^[A-Z][A-Z0-9_]*$")
_PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]*)\}")

# Kiểu tham số — danh sách đóng.
TYPE_NAME, TYPE_NAMES, SLOT_LABELS, STATUS_LABEL = "TYPE_NAME", "TYPE_NAMES", "SLOT_LABELS", "STATUS_LABEL"
KINDS = {TYPE_NAME: "scalar", TYPE_NAMES: "list", SLOT_LABELS: "list", STATUS_LABEL: "scalar"}

# Mã khuôn mà mã dùng. File phải có ĐÚNG tập này (thiếu một mã là #23 đỏ; thừa một khuôn không ai dùng cũng đỏ — khuôn mồ côi là nợ).
CLARIFY_TYPE, CLARIFY_TYPE_NO_CANDIDATE, CLARIFY_LIMIT_REACHED = "CLARIFY_TYPE", "CLARIFY_TYPE_NO_CANDIDATE", "CLARIFY_LIMIT_REACHED"
ASK_SLOT, ASK_SLOT_RETRY, ASK_PURPOSE_RETRY = "ASK_SLOT", "ASK_SLOT_RETRY", "ASK_PURPOSE_RETRY"
CONFIRM_PROPOSALS, OFFER_SUBMIT = "CONFIRM_PROPOSALS", "OFFER_SUBMIT"
OUT_OF_SCOPE_KNOWN, OUT_OF_SCOPE_GENERIC, RESUME_STATUS = "OUT_OF_SCOPE_KNOWN", "OUT_OF_SCOPE_GENERIC", "RESUME_STATUS"
ERROR_BUSY, BUDGET_LIMIT = "ERROR_BUSY", "BUDGET_LIMIT"
REQUIRED_IDS = frozenset({CLARIFY_TYPE, CLARIFY_TYPE_NO_CANDIDATE, CLARIFY_LIMIT_REACHED, ASK_SLOT, ASK_SLOT_RETRY, ASK_PURPOSE_RETRY, CONFIRM_PROPOSALS, OFFER_SUBMIT,
                          OUT_OF_SCOPE_KNOWN, OUT_OF_SCOPE_GENERIC, RESUME_STATUS, ERROR_BUSY, BUDGET_LIMIT})
# `PendingQuestion.kind` → khuôn mặc định của nó (mục State schema của 03-agents.md). `OFFER_NEXT_INTENT` và `EXPLAIN_TERMINAL` là khuôn của Sprint 2.
PENDING_KIND_TEMPLATES = {"CLARIFY_TYPE": CLARIFY_TYPE, "ASK_SLOT": ASK_SLOT, "CONFIRM_PROPOSALS": CONFIRM_PROPOSALS, "OFFER_SUBMIT": OFFER_SUBMIT}


class ReplyTemplateError(Exception):
    """Chỉ mang mã (và tên khuôn/tham số) — không bao giờ giá trị."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class Template:
    text: str
    params: Mapping[str, str]  # tên tham số → kiểu


def _join(items: Sequence[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " và " + items[-1]


class Templates:
    def __init__(self, templates: Mapping[str, Template]) -> None:
        self._templates = dict(templates)

    def __contains__(self, template_id: str) -> bool:
        return template_id in self._templates

    def ids(self) -> frozenset[str]:
        return frozenset(self._templates)

    def render(self, template_id: str, params: Mapping[str, Any] | None = None) -> str:
        template = self._templates.get(template_id)
        if template is None:
            raise ReplyTemplateError("TEMPLATE_UNKNOWN", template_id[:40])
        given = dict(params or {})
        if set(given) != set(template.params):
            raise ReplyTemplateError("PARAM_MISMATCH", template_id)
        values: dict[str, str] = {}
        for name, kind in template.params.items():
            value = given[name]
            if KINDS[kind] == "scalar":
                if not isinstance(value, str) or not value.strip():
                    raise ReplyTemplateError("PARAM_KIND", f"{template_id}:{name}")
                values[name] = value
            else:
                if isinstance(value, str) or not isinstance(value, Sequence) or not value or not all(isinstance(v, str) and v.strip() for v in value):
                    raise ReplyTemplateError("PARAM_KIND", f"{template_id}:{name}")  # danh sách rỗng ở khuôn đòi danh sách cũng là lỗi
                values[name] = _join(list(value))
        return _PLACEHOLDER.sub(lambda m: values[m.group(1)], template.text)


def parse(raw: Any) -> Templates:
    """Kiểm và dựng từ dữ liệu JSON đã đọc. Ném `ReplyTemplateError` với mã đầu tiên gặp — dùng cho nạp lúc chạy; #23 dùng `check` để gom."""
    codes = _problems(raw)
    if codes:
        raise ReplyTemplateError(codes[0].split(":", 1)[0], codes[0].split(":", 1)[1] if ":" in codes[0] else None)
    return Templates({tid: Template(t["text"], dict(t["params"])) for tid, t in raw["templates"].items()})


def _problems(raw: Any) -> list[str]:
    if not isinstance(raw, dict) or raw.get("schema_version") != SCHEMA_VERSION or not isinstance(raw.get("templates"), dict):
        return ["SCHEMA_INVALID"]
    codes: list[str] = []
    templates: dict[str, Any] = raw["templates"]
    for tid in sorted(REQUIRED_IDS - set(templates)):
        codes.append(f"TEMPLATE_MISSING:{tid}")
    for tid in sorted(set(templates) - REQUIRED_IDS):
        codes.append(f"TEMPLATE_UNUSED:{tid[:40]}")
    for tid, t in templates.items():
        if not isinstance(tid, str) or not _ID.match(tid):
            codes.append(f"ID_FORMAT:{str(tid)[:40]}")
            continue
        if not isinstance(t, dict) or not isinstance(t.get("text"), str) or not isinstance(t.get("params"), dict):
            codes.append(f"TEMPLATE_SHAPE:{tid}")
            continue
        text, params = t["text"], t["params"]
        if not text.strip():
            codes.append(f"TEXT_EMPTY:{tid}")
        if len(text) > MAX_TEXT_CHARS:
            codes.append(f"TEXT_TOO_LONG:{tid}")
        if any(kind not in KINDS for kind in params.values()):
            codes.append(f"PARAM_KIND_UNKNOWN:{tid}")
        names = set(_PLACEHOLDER.findall(text))
        if names != set(params):
            codes.append(f"PARAM_MISMATCH:{tid}")
        if "{" in _PLACEHOLDER.sub("", text) or "}" in _PLACEHOLDER.sub("", text):
            codes.append(f"TEXT_BRACE:{tid}")  # `{` hay `}` lạ — không phải tham số hợp lệ
    return codes


def check(path: Path = DEFAULT_PATH) -> tuple[str, ...]:
    """Mọi mã lỗi của file khuôn (rỗng = hợp lệ). Mã mang tên khuôn/tham số, không mang giá trị. Dùng cho bước kiểm khởi động #23."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return ("FILE_UNREADABLE",)
    except ValueError:
        return ("JSON_INVALID",)
    return tuple(_problems(raw))


def load(path: Path = DEFAULT_PATH) -> Templates:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        raise ReplyTemplateError("FILE_UNREADABLE") from None
    except ValueError:
        raise ReplyTemplateError("JSON_INVALID") from None
    return parse(raw)
