"""Máy trạng thái `request` (`bo19.domain.request_machine`) khớp sơ đồ Mermaid của 00-domain.md và danh sách trạng thái của DDL — B5.

Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_request_machine -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import re
import unittest
from pathlib import Path

from bo19.domain import request_machine as rm

ROOT = Path(__file__).resolve().parents[2]


def diagram_edges() -> tuple[set[tuple[str, str]], set[str]]:
    """Cạnh và trạng thái cuối của sơ đồ ở mục Vòng đời `request` của 00-domain.md (sơ đồ đầu tiên sau tiêu đề đó)."""
    text = (ROOT / "docs" / "design" / "00-domain.md").read_text(encoding="utf-8")
    section = text.split("### 5.1 Vòng đời `request`", 1)[1]
    block = section.split("```mermaid", 1)[1].split("```", 1)[0]
    edges, terminal = set(), set()
    for line in block.splitlines():
        m = re.match(r"\s+(\[\*\]|\w+) --> (\[\*\]|\w+)", line)
        if not m:
            continue
        a, b = m.groups()
        if b == "[*]":
            terminal.add(a)
        elif a != "[*]":
            edges.add((a, b))
    return edges, terminal


class KhopSoDo(unittest.TestCase):
    def test_canh_cua_bang_bang_canh_cua_so_do(self):
        edges, _ = diagram_edges()
        table = {(a, b) for a, targets in rm.REQUEST_TRANSITIONS.items() for b in targets}
        self.assertEqual(table, edges)
        self.assertEqual(len(edges), 14)  # đếm lại bằng mắt: sơ đồ có 14 cạnh giữa các trạng thái

    def test_trang_thai_cuoi_khop_so_do_va_khong_co_canh_ra(self):
        _, terminal = diagram_edges()
        self.assertEqual(set(rm.REQUEST_TERMINAL), terminal)
        for status in rm.REQUEST_TERMINAL:
            self.assertEqual(rm.REQUEST_TRANSITIONS[status], frozenset(), status)

    def test_trang_thai_khop_check_cua_ddl(self):
        ddl = (ROOT / "backend" / "migrations" / "schema" / "0001_initial.sql").read_text(encoding="utf-8")
        block = ddl.split("CONSTRAINT ck_request_status CHECK (status IN (", 1)[1].split("))", 1)[0]
        self.assertEqual(set(re.findall(r"'([A-Z_]+)'", block)), set(rm.REQUEST_STATUSES))
        self.assertEqual(set(rm.REQUEST_TRANSITIONS), set(rm.REQUEST_STATUSES))  # mỗi trạng thái có mặt như một khoá, kể cả trạng thái cuối

    def test_can_transition(self):
        self.assertTrue(rm.can_transition("DRAFT", "NEEDS_INFO"))
        self.assertTrue(rm.can_transition("NEEDS_INFO", "DRAFT"))
        for source, target in (("DRAFT", "APPROVED"), ("DRAFT", "DRAFT"), ("FULFILLED", "DRAFT"), ("EXPIRED", "DRAFT"), ("SUBMITTED", "DRAFT"),
                               ("APPROVED", "REJECTED"), ("NEEDS_INFO", "CANCELLED"), ("X", "DRAFT"), ("DRAFT", "X")):
            self.assertFalse(rm.can_transition(source, target), (source, target))

    def test_bang_khong_the_sua_tai_cho(self):
        with self.assertRaises(AttributeError):
            rm.REQUEST_TRANSITIONS["DRAFT"].add("APPROVED")  # frozenset


if __name__ == "__main__":
    unittest.main()
