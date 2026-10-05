"""Chốt chặn BẰNG CODE của bộ test (PO, 2026-10-05, sau sự cố gọi Groq thật ngoài kế hoạch — CHANGELOG, mục B4b):

1. **Mọi test chạy với `BO19_LLM_API_KEY` đã bị xoá** khỏi môi trường — xoá lại trước TỪNG test, nên dù người chạy export khoá hay một test tự đặt nó, test kế tiếp không thấy.
2. **Kết nối mạng thật bị chặn** (`socket`): chỉ cho phép loopback, socket Unix và host của PostgreSQL thử (`BO19_TEST_PG_SUPERUSER_DSN`). Mọi host khác — kể cả phân giải tên (`getaddrinfo`) —
   ném `NetworkBlocked`. `httpx.MockTransport` và ASGI không dùng socket nên không bị ảnh hưởng.

Mỗi file `test_*.py` phải nhập module này (`from tests import _guard`) — `tests/test_guard.py` quét và đòi điều đó, nên file test mới không thể quên.
Nhập module là đủ: nó tự cài khi import.
"""
from __future__ import annotations

import ipaddress
import os
import socket
import unittest

BLOCKED_ENV = ("BO19_LLM_API_KEY",)


class NetworkBlocked(Exception):
    """Test cố nối mạng ra ngoài. Mang tên host? Không — chỉ mã: tên host có thể là một phần của URL chứa bí mật."""


def _pg_hosts() -> set[str]:
    dsn = os.environ.get("BO19_TEST_PG_SUPERUSER_DSN", "")
    if not dsn:
        return set()
    try:
        from psycopg.conninfo import conninfo_to_dict
        host = conninfo_to_dict(dsn).get("host") or ""
    except Exception:  # noqa: BLE001
        return set()
    return {h for h in host.split(",") if h}


def _is_loopback(host: str) -> bool:
    if host in ("localhost", "localhost.localdomain"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


_resolved_ok: set[str] = set()  # địa chỉ IP phân giải ra từ host PostgreSQL được phép
_orig = {"connect": socket.socket.connect, "connect_ex": socket.socket.connect_ex, "getaddrinfo": socket.getaddrinfo}


def _host_allowed(host: str) -> bool:
    return _is_loopback(host) or host in _pg_hosts() or host in _resolved_ok


def _guarded_getaddrinfo(host, *args, **kwargs):  # type: ignore[no-untyped-def]
    if isinstance(host, bytes):
        host = host.decode("ascii", "ignore")
    if host is not None and not _host_allowed(str(host)):
        raise NetworkBlocked("NETWORK_BLOCKED:getaddrinfo")
    result = _orig["getaddrinfo"](host, *args, **kwargs)
    if host is not None and str(host) in _pg_hosts():
        _resolved_ok.update(item[4][0] for item in result)
    return result


def _check_address(address) -> None:  # type: ignore[no-untyped-def]
    if isinstance(address, (str, bytes)):  # socket Unix
        return
    if not _host_allowed(str(address[0])):
        raise NetworkBlocked("NETWORK_BLOCKED:connect")


def _guarded_connect(self, address):  # type: ignore[no-untyped-def]
    _check_address(address)
    return _orig["connect"](self, address)


def _guarded_connect_ex(self, address):  # type: ignore[no-untyped-def]
    _check_address(address)
    return _orig["connect_ex"](self, address)


_orig_run = unittest.TestCase.run


def _run_without_key(self, result=None):  # type: ignore[no-untyped-def]
    for name in BLOCKED_ENV:
        os.environ.pop(name, None)  # trước từng test, kể cả test async (IsolatedAsyncioTestCase gọi lại TestCase.run)
    return _orig_run(self, result)


def install() -> None:
    socket.getaddrinfo = _guarded_getaddrinfo  # type: ignore[assignment]
    socket.socket.connect = _guarded_connect  # type: ignore[method-assign]
    socket.socket.connect_ex = _guarded_connect_ex  # type: ignore[method-assign]
    unittest.TestCase.run = _run_without_key  # type: ignore[method-assign]
    for name in BLOCKED_ENV:
        os.environ.pop(name, None)


if socket.socket.connect is not _guarded_connect:
    install()
