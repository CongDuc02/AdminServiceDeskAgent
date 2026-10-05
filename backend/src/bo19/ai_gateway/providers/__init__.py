"""Adapter "chat completions dạng OpenAI" bằng `httpx` — ADR-035. Nơi duy nhất import `httpx` (contract `allowlist-gate`).

Bốn điều giữ cố định, mỗi điều có test và có trong phép thử đột biến (PO, 2026-10-05):

1. **Hạn chót tổng cho mỗi lời gọi** — một `asyncio.timeout` bao toàn bộ vòng thử: mọi lần thử, quãng nghỉ WV-05 và mọi lần chờ `retry-after`. Timeout từng pha của
   `httpx` KHÔNG đáng tin ở đây: `read` được tính lại sau mỗi byte nên một server nhỏ giọt từng byte không bao giờ chạm nó. Nó chỉ còn là chốt phụ.
2. **Lỗi provider chỉ để lại ba thứ:** mã HTTP, loại lỗi (`error.type`) và `code` (`error.code`) nếu có — mỗi chuỗi chỉ được giữ khi khớp khuôn ngắn. Thân response thô **không bao giờ**
   vào log, vào exception hay vào chuỗi nào: nó có thể trích lại input, kể cả `RES`. Exception ném `from None`: chuỗi nguyên nhân của `httpx` mang URL và có thể mang thân.
3. **Khoá API** nằm trong một đối tượng bọc `_Secret` — không vào `repr`, `str`, `vars` hay pickle của client; chỉ `Authorization` lúc gửi đọc nó. Provider trả 401 cũng không để lộ khoá.
4. **Không suy ra số token:** trường `usage` nào provider không trả thì để `None` (ADR-035, mục Decision).

Dạng request lấy từ nguồn gốc: `docs/reference/llm-groq-structured-request.md`. Thân lỗi của chat completions chưa có nguồn gốc (A-091): đọc dung thứ, không dựa vào để phân loại.
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any

import httpx

from bo19.ai_gateway.routing.profiles import ModelProfile
from bo19.config import working_values as wv

RATE_LIMITED, CALL_FAILED = "PROVIDER_RATE_LIMITED", "PROVIDER_CALL_FAILED"  # enum `provider_failure_subcode` của GLOSSARY.md
MAX_RESPONSE_BYTES = 1_048_576  # bảo vệ bộ nhớ trước một response lớn bất thường — giá trị tạm
_ERROR_BODY_BYTES = 16_384  # chỉ đọc đầu thân lỗi để tìm hai trường ngắn
_SHORT = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_TRANSIENT_STATUS = frozenset({429, 500, 502, 503, 504})


class _Secret:
    """Giữ một chuỗi bí mật: không `repr`, không `str`, không pickle. `reveal()` chỉ gọi lúc dựng header."""

    __slots__ = ("_v",)

    def __init__(self, value: str) -> None:
        self._v = value

    def reveal(self) -> str:
        return self._v

    def __repr__(self) -> str:
        return "<ẩn>"

    __str__ = __repr__

    def __reduce__(self) -> Any:
        raise TypeError("không tuần tự hoá được bí mật")

    def __copy__(self) -> Any:
        raise TypeError("không sao chép được bí mật")


class ProviderError(Exception):
    """Lỗi từ provider hoặc đường tới provider. Chỉ mang mã và số — không thân response, không URL, không header, không khoá."""

    def __init__(self, subcode: str, kind: str, http_status: int | None = None, error_type: str | None = None, error_code: str | None = None,
                 retry_after_seconds: int | None = None, attempts: int = 1) -> None:
        super().__init__(f"{subcode}:{kind}")
        self.subcode, self.kind, self.http_status = subcode, kind, http_status
        self.error_type, self.error_code, self.retry_after_seconds, self.attempts = error_type, error_code, retry_after_seconds, attempts

    code = property(lambda self: self.subcode)

    def log_fields(self) -> dict[str, Any]:
        # `error_type` là tên dành riêng của log (kiểu exception) — nên đổi tên trường của provider
        return {"subcode": self.subcode, "kind": self.kind, "http_status": self.http_status, "provider_error_type": self.error_type,
                "provider_error_code": self.error_code, "retry_after_seconds": self.retry_after_seconds, "attempts": self.attempts}


@dataclass(frozen=True)
class ProviderResponse:
    content: str
    prompt_tokens: int | None
    completion_tokens: int | None
    reasoning_tokens: int | None
    prompt_time: float | None
    completion_time: float | None


def _short(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        value = str(value)
    return value if isinstance(value, str) and _SHORT.match(value) else None


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0 else None


def _retry_after(headers: httpx.Headers) -> int | None:
    raw = headers.get("retry-after", "")
    return int(raw) if raw.isascii() and raw.isdigit() and len(raw) <= 6 else None  # giây (docs/reference/llm-groq.md mục 6d)


class _Transient(Exception):
    def __init__(self, error: ProviderError) -> None:
        self.error = error


class ProviderClient:
    def __init__(self, *, base_url: str, api_key: str | None, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._key = _Secret(api_key) if api_key else None
        self._transport = transport

    def __repr__(self) -> str:
        return "ProviderClient(api_key=<ẩn>)"  # không in cả base_url: người triển khai có thể đặt thông tin vào đường dẫn

    async def call(self, *, profile: ModelProfile, messages: list[dict[str, str]], schema_name: str, schema: dict[str, Any], total_deadline_s: float,
                   retry_after_cap_s: float | None = None) -> ProviderResponse:
        """Một lời gọi có hạn chót tổng. `retry_after_cap_s` — trần chờ `retry-after` (WV-19, trong job); `None` thì chỉ hạn chót tổng chặn."""
        if self._key is None:
            raise ProviderError(CALL_FAILED, "NO_API_KEY", attempts=0)
        loop = asyncio.get_running_loop()
        started, attempts = loop.time(), 0
        try:
            async with asyncio.timeout(total_deadline_s):
                while True:
                    attempts += 1
                    try:
                        return await self._once(profile, messages, schema_name, schema, total_deadline_s)
                    except _Transient as t:
                        error = t.error
                        error.attempts = attempts
                        if attempts > wv.LLM_RETRY_COUNT:
                            raise error from None
                        remaining = total_deadline_s - (loop.time() - started)
                        wait = float(wv.LLM_RETRY_PAUSE_SECONDS)
                        if error.retry_after_seconds is not None:
                            # chờ theo `retry-after` CHỈ khi nó nhỏ hơn thời gian còn lại (và trong job, không vượt WV-19) — lần chờ này là lần thử lại duy nhất
                            if error.retry_after_seconds >= remaining or (retry_after_cap_s is not None and error.retry_after_seconds > retry_after_cap_s):
                                raise error from None
                            wait = float(error.retry_after_seconds)
                        if wait >= remaining:
                            raise error from None
                        await asyncio.sleep(wait)
        except TimeoutError:
            raise ProviderError(CALL_FAILED, "DEADLINE", attempts=attempts) from None

    async def _once(self, profile: ModelProfile, messages: list[dict[str, str]], schema_name: str, schema: dict[str, Any], backstop_s: float) -> ProviderResponse:
        body = {
            "model": profile.model,
            "messages": messages,
            "stream": False,  # structured outputs không dùng chung với streaming (docs/reference/llm-groq.md mục 6b)
            "response_format": {"type": "json_schema", "json_schema": {"name": schema_name, "strict": True, "schema": schema}},
            **profile.params,  # tham số riêng của model, đã qua bước kiểm #21 — không bao giờ `logprobs`, `logit_bias`, `top_logprobs`, `n`
        }
        headers = {"Authorization": f"Bearer {self._key.reveal()}", "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=httpx.Timeout(backstop_s), follow_redirects=False, trust_env=False) as client:
                async with client.stream("POST", self._url, headers=headers, content=json.dumps(body, ensure_ascii=False).encode("utf-8")) as response:
                    status = response.status_code
                    limit = MAX_RESPONSE_BYTES if status == 200 else _ERROR_BODY_BYTES
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        chunks.append(chunk)
                        size += len(chunk)
                        if size > limit:
                            break
                    retry_after = _retry_after(response.headers)
                    raw = b"".join(chunks)
        except httpx.HTTPError:
            raise _Transient(ProviderError(CALL_FAILED, "CONNECTION")) from None  # chuỗi nguyên nhân mang URL — bỏ
        if status == 200:
            return self._parse_ok(raw, size > limit)
        error_type, error_code = self._parse_error(raw)
        error = ProviderError(RATE_LIMITED if status == 429 else CALL_FAILED, "HTTP_STATUS", status, error_type, error_code, retry_after if status == 429 else None)
        if status in _TRANSIENT_STATUS:
            raise _Transient(error)
        raise error

    @staticmethod
    def _parse_error(raw: bytes) -> tuple[str | None, str | None]:
        """Đọc dung thứ `error.type` và `error.code` (A-091); mọi thứ khác trong thân bị bỏ. Không bao giờ ném."""
        try:
            data = json.loads(raw)
            err = data.get("error") if isinstance(data, dict) else None
            if isinstance(err, dict):
                return _short(err.get("type")), _short(err.get("code"))
        except (ValueError, UnicodeDecodeError, RecursionError):
            pass
        return None, None

    @staticmethod
    def _parse_ok(raw: bytes, too_large: bool) -> ProviderResponse:
        try:
            if too_large:
                raise ValueError
            data = json.loads(raw)
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise ValueError
            usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
            details = usage.get("completion_tokens_details") if isinstance(usage.get("completion_tokens_details"), dict) else {}
            return ProviderResponse(content, _int(usage.get("prompt_tokens")), _int(usage.get("completion_tokens")), _int(details.get("reasoning_tokens")),
                                    _num(usage.get("prompt_time")), _num(usage.get("completion_time")))
        except (ValueError, KeyError, IndexError, TypeError, UnicodeDecodeError, AttributeError, RecursionError):
            raise ProviderError(CALL_FAILED, "BAD_RESPONSE", 200) from None
