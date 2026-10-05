"""Dữ liệu GIẢ cho phép đo — mọi nội dung là văn bản bịa, có nhãn "(giả)" (PO, 2026-10-05; A-080; `docs/testing/nguoi-thu.md`).

Tin nhắn trần dài đúng 2.000 ký tự (WV-15), tiếng Việt CÓ DẤU, văn phong như tin nhắn của nhân viên thật — không dấu thì số token thấp hơn thực tế
(PO, 2026-10-05). Không có tên người, mã nhân viên, số căn cước hay cơ quan có thật.
"""
from __future__ import annotations

WV15_CHARS = 2000

_SENTENCES = (
    "Chào phòng hành chính ạ, em là nhân viên giả số 01 (giả), bên phòng kế hoạch (giả). ",
    "Em nhắn để nhờ chị làm giúp em cái giấy xác nhận đang công tác tại công ty để em nộp bổ sung hồ sơ vay vốn ở ngân hàng thử nghiệm (giả). ",
    "Bên ngân hàng (giả) họ bảo cần bản có đóng dấu đỏ của công ty, ghi rõ chức danh và thời gian em làm việc, em nghĩ lấy hai bản là đủ nhưng chị cứ chuẩn bị giúp em ba bản cho chắc ạ. ",
    "Hôm trước em có hỏi anh bên bộ phận nhân sự (giả) thì anh bảo giấy này bên hành chính cấp chứ không phải bên nhân sự, nên hôm nay em mới nhắn cho chị. ",
    "Thật ra em cũng đang tính xin thêm một cái giấy giới thiệu để tuần sau đi làm việc với một đơn vị đối tác (giả) ở tỉnh khác, nhưng cái đó em chưa chốt ngày, để em hỏi lại sếp rồi báo chị sau nhé. ",
    "Nếu được thì chị cho em hẹn lấy vào chiều thứ Năm hoặc sáng thứ Sáu, vì thứ Hai tuần sau em phải nộp hồ sơ rồi, em sợ không kịp. ",
    "Em xin lỗi vì nhắn hơi dài và hơi lộn xộn, tại em cũng mới làm quen với cái hệ thống này (giả). Mong chị giúp đỡ, em cảm ơn chị nhiều lắm ạ! ",
)


def bare_message(chars: int = WV15_CHARS) -> str:
    """Tin nhắn giả dài đúng `chars` ký tự: các câu trên lặp lại rồi cắt, kết thúc bằng nhãn "(giả)"."""
    text = ""
    while len(text) < chars:
        text += "".join(_SENTENCES)
    tail = " (giả)"
    return text[: chars - len(tail)] + tail


CATALOG = [
    {"code": "WORK_CONFIRMATION", "support_status": "SUPPORTED", "name_vi": "Giấy xác nhận công tác (giả)",
     "description": "Xác nhận nhân viên đang làm việc tại tổ chức, dùng cho hồ sơ vay vốn, thuê nhà hoặc thủ tục hành chính khác (giả).",
     "example_phrases": ["xin giấy xác nhận đang làm việc", "cần giấy xác nhận công tác để nộp ngân hàng"]},
    {"code": "INTRODUCTION_LETTER", "support_status": "SUPPORTED", "name_vi": "Giấy giới thiệu (giả)",
     "description": "Giới thiệu nhân viên đến làm việc với cơ quan hoặc đơn vị đối tác bên ngoài (giả).",
     "example_phrases": ["xin giấy giới thiệu đi làm việc với đối tác", "cần giấy giới thiệu đến sở"]},
    {"code": "ROOM_BOOKING", "support_status": "KNOWN_UNSUPPORTED", "name_vi": "Đặt phòng họp (giả)",
     "description": "Đặt phòng họp hoặc phòng đào tạo cho một khoảng thời gian (giả).",
     "example_phrases": ["đặt phòng họp chiều mai", "mượn phòng đào tạo"]},
    {"code": "SEAL_REQUEST", "support_status": "KNOWN_UNSUPPORTED", "name_vi": "Xin đóng dấu (giả)",
     "description": "Xin đóng dấu vào văn bản của đơn vị khác hoặc văn bản ngoài (giả).",
     "example_phrases": ["xin đóng dấu vào hợp đồng", "nhờ đóng dấu giáp lai"]},
    {"code": "VEHICLE_REQUEST", "support_status": "KNOWN_UNSUPPORTED", "name_vi": "Xin xe công tác (giả)",
     "description": "Đăng ký xe của cơ quan cho chuyến đi công tác (giả).",
     "example_phrases": ["xin xe đi công tác", "đăng ký xe đi tỉnh"]},
    {"code": "LEAVE_CERTIFICATE", "support_status": "KNOWN_UNSUPPORTED", "name_vi": "Giấy xác nhận nghỉ phép (giả)",
     "description": "Xác nhận thời gian nghỉ phép của nhân viên (giả).",
     "example_phrases": ["xin giấy xác nhận nghỉ phép", "cần xác nhận ngày nghỉ"]},
]

P2_MESSAGE = "Gửi tới Công ty Thử Nghiệm (giả), mục đích bổ sung hồ sơ vay vốn mua nhà (giả), em cần hai bản ạ."
P2_SLOT_SPECS = [
    {"name": "purpose", "data_type": "STRING", "description": "Mục đích xin giấy xác nhận (giả)"},
    {"name": "recipient_org", "data_type": "STRING", "description": "Tên cơ quan hoặc tổ chức nhận (giả)"},
    {"name": "copies_count", "data_type": "INTEGER", "description": "Số bản cần cấp (giả)"},
]
P4_INPUTS = {"purpose": "bổ sung hồ sơ vay vốn mua nhà tại ngân hàng thử nghiệm (giả)", "variable_guidance": "Một đến hai câu, văn phong hành chính, nêu mục đích sử dụng giấy (giả).",
             "request_type": "WORK_CONFIRMATION"}
PING = "ping (giả)"
