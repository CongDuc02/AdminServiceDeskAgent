"""State của `intake_graph` — contract ở mục State schema của 03-agents.md (ADR-008).

**Không trường nào mang giá trị slot, văn bản tin nhắn, văn bản do LLM sinh hay `change_reason`** — chỉ id, mã enum, tên slot, bộ đếm. Mọi `str` dưới đây là id hoặc mã.
`schema_version` đầu tiên là 1 (chưa thread nào chạy, không có chuỗi nâng cấp — mục Schema state đổi giữa chừng của 03-agents.md).
Mọi node ra quyết định **đọc lại trạng thái từ DB**; state không bao giờ là nguồn sự thật về trạng thái của `request`.
"""
from __future__ import annotations

from typing import Literal, TypedDict

SCHEMA_VERSION = 1

RequestTypeCode = str
SlotName = str
RequestStatusCode = str

IntentResult = Literal["SUPPORTED", "AMBIGUOUS", "OUT_OF_SCOPE", "TYPE_CHANGED", "MULTIPLE", "UNPARSEABLE"]
PendingKind = Literal["CLARIFY_TYPE", "ASK_SLOT", "CONFIRM_PROPOSALS", "OFFER_SUBMIT", "OFFER_NEXT_INTENT", "EXPLAIN_TERMINAL"]


class PendingQuestion(TypedDict):
    kind: PendingKind
    template_id: str  # id khuôn câu trong cấu hình, không phải văn bản câu
    slot_names: list[SlotName]
    candidate_types: list[RequestTypeCode]


class PendingIntent(TypedDict):
    request_type: RequestTypeCode | None  # None = ngoài phạm vi
    source_message_id: str  # tham chiếu chat_message, không chép nội dung


class IntakeState(TypedDict):
    schema_version: int
    trace_id: str
    chat_session_id: str
    actor_employee_id: str
    current_message_id: str
    active_request_id: str | None
    active_request_type: RequestTypeCode | None
    intent_result: IntentResult | None
    unsupported_type: RequestTypeCode | None
    procedure_store: Literal["READY", "NOT_READY"] | None
    pending_intents: list[PendingIntent]
    pending_question: PendingQuestion | None
    clarification_count: int
    last_seen_request_status: RequestStatusCode | None
    missing_slots: list[SlotName]
    rejected_slots: list[SlotName]
    rejection_codes: list[str]  # cùng thứ tự rejected_slots: "<mã>" hoặc "<mã>:<mã con>" — chỉ mã (B6b, PO Q3)
    proposed_slots: list[SlotName]
    retrieved_chunk_ids: list[str]
    selected_chunk_ids: list[str]
    reply_template_id: str | None
    last_error_code: str | None


# Trường được đặt lại ở ĐẦU mỗi lượt (`load_turn`) — chúng mô tả lượt hiện tại, không phải cuộc hội thoại. Phần còn lại (đếm làm rõ, request đang mở, `pending_intents`, mốc trạng thái đã thấy)
# sống qua các lượt nhờ checkpoint của thread `intake:{chat_session_id}`.
PER_TURN_FIELDS: dict[str, object] = {
    "intent_result": None,
    "unsupported_type": None,
    "procedure_store": None,
    "pending_question": None,
    "missing_slots": [],
    "rejected_slots": [],
    "rejection_codes": [],
    "proposed_slots": [],
    "retrieved_chunk_ids": [],
    "selected_chunk_ids": [],
    "reply_template_id": None,
    "last_error_code": None,
}


def initial_state(*, trace_id: str, chat_session_id: str, actor_employee_id: str, current_message_id: str) -> IntakeState:
    """Giá trị của một thread mới. Với thread đã có, runner chỉ đưa bốn trường định danh của lượt — phần còn lại lấy từ checkpoint."""
    return IntakeState(
        schema_version=SCHEMA_VERSION, trace_id=trace_id, chat_session_id=chat_session_id, actor_employee_id=actor_employee_id, current_message_id=current_message_id,
        active_request_id=None, active_request_type=None, intent_result=None, unsupported_type=None, procedure_store=None, pending_intents=[], pending_question=None,
        clarification_count=0, last_seen_request_status=None, missing_slots=[], rejected_slots=[], rejection_codes=[], proposed_slots=[], retrieved_chunk_ids=[], selected_chunk_ids=[],
        reply_template_id=None, last_error_code=None)
