"""Thứ `api` cần từ composition root, gói thành một đối tượng — `entrypoints.api_main` dựng, test dựng bản của test."""
from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import Request

from bo19.api.auth.hasher import PasswordVerifier
from bo19.api.files_gate import FileFetchLimits
from bo19.api.turns import TurnSupervisor
from bo19.persistence.pool import Pool
from bo19.tool_layer.storage import ObjectStorage  # tên do tool_layer.storage mang ra — api không import `bo19.object_storage` (contract api-surface)


@dataclass(frozen=True)
class AppState:
    pool: Pool
    session_secret: str = field(repr=False)  # secret — không bao giờ vào repr hay log
    verifier: PasswordVerifier = field(repr=False)  # một cho cả tiến trình: trần verify đồng thời (WV-16b) là của đối tượng này
    supervisor: TurnSupervisor | None = None  # B6b — bộ giám sát lượt chat (ADR-016); thiếu thì `POST …/turns` không chạy được. `entrypoints.api_main` dựng
    turn_deadline_s: int = 20  # WV-02 — hạn chót của một lượt; cộng `turn_margin_s` (WV-03) là ngưỡng "lượt trước còn chạy" (TURN_IN_PROGRESS) và "đã quá hạn" (TURN_NOT_FINISHED)
    turn_margin_s: int = 10
    storage: ObjectStorage | None = None  # B8b — object storage cho `stored_file_fetch`; `None` (nhóm biến chưa cấu hình, bước kiểm #14 cảnh báo) thì endpoint tải file trả FILE_UNAVAILABLE. `entrypoints.api_main` dựng
    file_fetch: FileFetchLimits = FileFetchLimits()  # B8c — WV-26..30: số lượt tải đồng thời, chờ chỗ, hạn chót, Retry-After; test dựng giá trị nhỏ
    drain_s: float = 25.0  # cửa sổ chờ lượt đang chạy khi tắt tiến trình (`BO19_SHUTDOWN_DELAY_SECONDS`)


def get_state(request: Request) -> AppState:
    return request.app.state.bo19
