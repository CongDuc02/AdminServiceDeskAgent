"""Thứ `api` cần từ composition root, gói thành một đối tượng — `entrypoints.api_main` dựng, test dựng bản của test."""
from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import Request

from bo19.api.auth.hasher import PasswordVerifier
from bo19.persistence.pool import Pool


@dataclass(frozen=True)
class AppState:
    pool: Pool
    session_secret: str = field(repr=False)  # secret — không bao giờ vào repr hay log
    verifier: PasswordVerifier = field(repr=False)  # một cho cả tiến trình: trần verify đồng thời (WV-16b) là của đối tượng này


def get_state(request: Request) -> AppState:
    return request.app.state.bo19
