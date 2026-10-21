"""Lỗi chuẩn hoá của `api` — mã lỗi nội bộ → `error_code`; mã không có ánh xạ thì `INTERNAL_ERROR` (mục Lỗi chuẩn hoá và Mã lỗi của 05-api.md).

Mọi response lỗi, ở mọi mã HTTP, có ba trường `error_code`, `message`, `trace_id` và tuỳ chọn `details` (mục 1.6 của 05-api.md).
`message` là câu cố định bằng tiếng Việt từ danh mục này — **không bao giờ** dựng từ dữ liệu của request hay của exception; `details` chỉ mang tên trường,
mã con và số đếm. Mã lỗi nội bộ (mã của tool, `POOL_EXHAUSTED`, `CHECK_VIOLATION`, …) không bao giờ ra khỏi `api` (mục Mã lỗi của tool và thao tác).

`CATALOG` chỉ chứa các mã mà code đã dùng; `tests/test_api_errors.py` đọc lại bảng ở mục Danh mục `error_code` của `05-api.md` và đòi mã HTTP khớp.
Thêm một mã vào đây là thêm một dòng cùng test, không sửa bảng ở tài liệu.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler as _default_http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from bo19.observability.log import get_logger
from bo19.observability.trace import new_trace_id, trace_scope

log = get_logger("bo19.api")

TRACE_SCOPE_KEY = "bo19_trace_id"  # khoá trong ASGI scope — `TraceMiddleware` đặt; bộ xử lý lỗi của lớp ngoài cùng cũng đọc được
_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


@dataclass(frozen=True)
class ErrorSpec:
    http: int
    message: str
    variants: dict[str, str] = field(default_factory=dict)  # câu thay thế CỐ ĐỊNH theo tên biến thể — vẫn không dựng từ dữ liệu (ví dụ `TURN_NOT_FINISHED`)


CATALOG: dict[str, ErrorSpec] = {
    "UNAUTHENTICATED": ErrorSpec(401, "Bạn chưa đăng nhập hoặc phiên đã hết hạn. Hãy đăng nhập lại."),
    "INVALID_CREDENTIALS": ErrorSpec(401, "Mã nhân viên hoặc mật khẩu không đúng. Hãy kiểm lại thông tin đăng nhập."),
    "CSRF_HEADER_MISSING": ErrorSpec(403, "Yêu cầu thiếu thông tin bảo vệ của trang. Hãy tải lại trang rồi thử lại."),
    "PERMISSION_DENIED": ErrorSpec(403, "Bạn không có quyền thực hiện thao tác này. Hãy liên hệ Phòng Hành chính nếu cần quyền."),
    "SELF_APPROVAL_BLOCKED": ErrorSpec(403, "Bạn là người thụ hưởng của yêu cầu này nên không thực hiện thao tác này được. Hãy chuyển cho người khác xử lý."),
    "NOT_FOUND": ErrorSpec(404, "Không tìm thấy nội dung được yêu cầu. Hãy kiểm lại đường dẫn."),
    "NOT_ACCEPTABLE": ErrorSpec(406, "Yêu cầu này phải gửi kèm Accept: text/event-stream."),
    "IDEMPOTENCY_KEY_REQUIRED": ErrorSpec(400, "Yêu cầu thiếu mã chống gửi trùng (Idempotency-Key). Hãy tải lại trang rồi thử lại."),
    "IDEMPOTENCY_KEY_CONFLICT": ErrorSpec(409, "Mã chống gửi trùng này đã được dùng cho một thao tác khác. Hãy thử lại thao tác."),
    "CHAT_SESSION_CLOSED": ErrorSpec(409, "Cuộc trò chuyện này đã đóng. Hãy mở cuộc trò chuyện mới."),
    "STATE_CONFLICT": ErrorSpec(409, "Dữ liệu đã thay đổi kể từ lúc bạn mở. Hãy tải lại để xem trạng thái mới."),
    "DOCUMENT_AWAITING_TAKEOVER": ErrorSpec(409, "Văn bản đang dừng chờ Phòng Hành chính xử lý. Hãy chờ rồi thử lại."),
    "REQUEST_NOT_EDITABLE": ErrorSpec(409, "Yêu cầu không còn ở trạng thái bổ sung được. Hãy tải lại yêu cầu."),
    "SLOT_NOT_PROPOSED": ErrorSpec(409, "Mục này không có giá trị nào đang chờ bạn xác nhận. Hãy tải lại yêu cầu."),
    "SLOT_VALUE_STALE": ErrorSpec(409, "Giá trị đề xuất đã thay đổi kể từ lúc hiển thị. Hãy xem lại giá trị mới rồi xác nhận."),
    "TURN_IN_PROGRESS": ErrorSpec(409, "Hệ thống đang trả lời tin nhắn trước của bạn. Hãy chờ một chút rồi gửi tiếp."),
    "TURN_NOT_FINISHED": ErrorSpec(409, "Tin nhắn của bạn đã được lưu. Hệ thống chưa trả lời xong — vui lòng chờ một chút rồi tải lại.",
                                   {"abandoned": "Tin nhắn của bạn đã được lưu nhưng hệ thống không trả lời được. Vui lòng gửi lại nội dung trong một tin nhắn mới."}),
    "PAYLOAD_TOO_LARGE": ErrorSpec(413, "Dữ liệu gửi lên vượt giới hạn cho phép. Hãy gửi lại nội dung nhỏ hơn."),
    "VALIDATION_FAILED": ErrorSpec(422, "Dữ liệu gửi lên chưa đúng. Hãy sửa các trường được nêu rồi gửi lại."),
    "REQUEST_NOT_READY": ErrorSpec(422, "Yêu cầu chưa đủ thông tin để gửi. Hãy bổ sung hoặc xác nhận các mục được nêu."),
    "RATE_LIMITED": ErrorSpec(429, "Đã thử đăng nhập quá nhiều lần. Hãy chờ một lúc rồi thử lại."),
    "FILE_UNAVAILABLE": ErrorSpec(503, "Chưa tải được tệp lúc này. Hãy liên hệ Phòng Hành chính."),
    "INTERNAL_ERROR": ErrorSpec(500, "Hệ thống gặp lỗi không lường trước. Hãy thử lại sau; nếu lặp lại, hãy báo mã trace_id."),
}

# Mã lỗi nội bộ → error_code lộ ra client. Mã không có trong bảng → INTERNAL_ERROR.
INTERNAL_TO_API: dict[str, str] = {"PERMISSION_DENIED": "PERMISSION_DENIED"}  # tool từ chối vì thiếu permission → 403; mã còn lại do router dịch rõ ràng (cần `details`)


class ApiError(Exception):
    """Lỗi có chủ đích của `api`. `details` chỉ mang tên, mã con, số đếm — không giá trị."""

    def __init__(self, error_code: str, details: dict[str, Any] | None = None, headers: dict[str, str] | None = None, variant: str | None = None) -> None:
        super().__init__(error_code)
        if error_code not in CATALOG:
            raise ValueError(f"error_code chưa có trong danh mục của api: {error_code}")
        if variant is not None and variant not in CATALOG[error_code].variants:
            raise ValueError(f"biến thể chưa có trong danh mục: {error_code}/{variant}")
        self.error_code = error_code
        self.details = details
        self.headers = headers
        self.variant = variant


def api_code_for(internal_code: str | None) -> str:
    return INTERNAL_TO_API.get(internal_code or "", "INTERNAL_ERROR")


def _trace_id(request: Request) -> str:
    return request.scope.get(TRACE_SCOPE_KEY) or new_trace_id()


def error_envelope(trace_id: str, error_code: str, details: dict[str, Any] | None = None, variant: str | None = None) -> dict[str, Any]:
    spec = CATALOG[error_code]
    body: dict[str, Any] = {"error_code": error_code, "message": spec.variants[variant] if variant else spec.message, "trace_id": trace_id}
    if details:
        body["details"] = details
    return body


def error_response(request: Request, error_code: str, details: dict[str, Any] | None = None, headers: dict[str, str] | None = None, variant: str | None = None) -> JSONResponse:
    spec = CATALOG[error_code]
    body: dict[str, Any] = {"error_code": error_code, "message": spec.variants[variant] if variant else spec.message, "trace_id": _trace_id(request)}
    if details:
        body["details"] = details
    return JSONResponse(body, status_code=spec.http, headers=headers)


def _is_api_path(path: str) -> bool:
    return path == "/api" or path.startswith("/api/")


is_api_path = _is_api_path  # cho `api.static` — luật 404 phân đôi theo đúng hàm này


# Mã con của fields[].code (mục Danh mục error_code của 05-api.md) theo kiểu lỗi của pydantic. Không bao giờ chép `input` hay `msg`:
# giá trị đã gửi có thể là mật khẩu.
def _field_code(pydantic_type: str, ctx: dict | None = None) -> str:
    if pydantic_type == "missing":
        return "REQUIRED"
    # `SecretStr` (mật khẩu) báo `too_short` với `field_type = "Value"`; danh sách cũng `too_short` nhưng `field_type = "List"` — chỉ giá trị vô hướng là BLANK.
    if pydantic_type == "string_too_short" or (pydantic_type == "too_short" and (ctx or {}).get("field_type") == "Value"):
        return "BLANK"
    # `SecretStr` quá dài báo `too_long` với `field_type = "Value"` (như `too_short` ở trên); danh sách quá dài cũng `too_long` nhưng `field_type = "List"` → không phải TOO_LONG của chuỗi.
    if pydantic_type == "string_too_long" or (pydantic_type == "too_long" and (ctx or {}).get("field_type") == "Value"):
        return "TOO_LONG"
    if pydantic_type == "extra_forbidden":
        return "NOT_ALLOWED"
    if pydantic_type.startswith(("greater", "less")):
        return "OUT_OF_RANGE"
    return "INVALID_FORMAT"


def _fields(exc: RequestValidationError) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for err in exc.errors():
        loc = [str(x) for x in err.get("loc", ())]
        name = ".".join(loc[1:]) if len(loc) > 1 else (loc[0] if loc else "body")
        out.append({"field": name, "code": _field_code(str(err.get("type", "")), err.get("ctx"))})
    return out


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        return error_response(request, exc.error_code, exc.details, exc.headers, exc.variant)

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(request: Request, exc: StarletteHTTPException):
        if not _is_api_path(request.url.path):
            return await _default_http_exception_handler(request, exc)  # ngoài /api: tuyến lạ do `api.static` xử lý (B10a); không có bản build (test) thì mặc định của framework
        # 404 và 405 cùng là NOT_FOUND: danh mục không có mã 405, và 404 không để lộ thêm gì (O1-8).
        return error_response(request, "NOT_FOUND" if exc.status_code in (404, 405) else "INTERNAL_ERROR")

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(request, "VALIDATION_FAILED", {"fields": _fields(exc)})

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        internal = getattr(exc, "code", None)
        internal = internal if isinstance(internal, str) and _CODE_RE.match(internal) else None
        trace_id = request.scope.setdefault(TRACE_SCOPE_KEY, new_trace_id())
        response = error_response(request, api_code_for(internal))
        # Bộ xử lý này chạy ở lớp ngoài cùng, ngoài `trace_scope` của TraceMiddleware: mở lại đúng trace_id của request để log và envelope khớp nhau.
        with trace_scope(trace_id):
            log.error("API_UNHANDLED_ERROR", exc=exc, internal_code=internal)  # chỉ kiểu lỗi và mã — không thông điệp
        return response
