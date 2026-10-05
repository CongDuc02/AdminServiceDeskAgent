"""Model request/response của nhóm Phiên đăng nhập — khớp `LoginBody`, `Me` ở `contracts/openapi.yaml` (mục Phiên đăng nhập của 05-api.md)."""
from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class LoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employee_code: str = Field(min_length=1)
    password: SecretStr = Field(min_length=1)  # `format: password`, `writeOnly` — không vào repr, không vào log


class MeEmployee(BaseModel):
    id: uuid.UUID
    employee_code: str
    full_name: str
    department_code: str
    department_name: str
    job_title: str


class Me(BaseModel):
    employee: MeEmployee
    permissions: list[str]  # permission hiệu lực: gói vai trò cộng quyền cấp lẻ còn hiệu lực — không phải tên vai trò (D-005)
    operating_mode: Literal["NON_PRODUCTION", "PRODUCTION"]
