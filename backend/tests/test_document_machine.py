"""Máy trạng thái `document` (`bo19.domain.document_machine`) khớp sơ đồ Mermaid của 00-domain.md và danh sách trạng thái của DDL — B9a.

Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_document_machine -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import re
import unittest
from pathlib import Path

from bo19.domain import document_machine as dm

ROOT = Path(__file__).resolve().parents[2]


def diagram_edges() -> tuple[set[tuple[str, str]], set[str]]:
    """Cạnh và trạng thái cuối của sơ đồ ở mục Vòng đời `document` của 00-domain.md (sơ đồ đầu tiên sau tiêu đề đó)."""
    text = (ROOT / "docs" / "design" / "00-domain.md").read_text(encoding="utf-8")
    section = text.split("### 5.2 Vòng đời `document`", 1)[1]
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
        table = {(a, b) for a, targets in dm.DOCUMENT_TRANSITIONS.items() for b in targets}
        self.assertEqual(table, edges)
        self.assertEqual(len(edges), 21)  # đếm lại bằng mắt: sơ đồ có 21 cạnh giữa các trạng thái

    def test_trang_thai_cuoi_khop_so_do_va_khong_co_canh_ra(self):
        _, terminal = diagram_edges()
        self.assertEqual(set(dm.DOCUMENT_TERMINAL), terminal)
        for status in dm.DOCUMENT_TERMINAL:
            self.assertEqual(dm.DOCUMENT_TRANSITIONS[status], frozenset(), status)

    def test_trang_thai_khop_check_cua_ddl(self):
        ddl = (ROOT / "backend" / "migrations" / "schema" / "0001_initial.sql").read_text(encoding="utf-8")
        block = ddl.split("CONSTRAINT ck_document_status CHECK (status IN (", 1)[1].split("))", 1)[0]
        self.assertEqual(set(re.findall(r"'([A-Z_]+)'", block)), set(dm.DOCUMENT_STATUSES))
        self.assertEqual(set(dm.DOCUMENT_TRANSITIONS), set(dm.DOCUMENT_STATUSES))

    def test_bat_bien_khong_co_duong_tu_draft_toi_issued_ma_khong_qua_pending_approval(self):
        """Bất biến 1 của vòng đời (00-domain.md): từ DRAFT tới ISSUED phải qua PENDING_APPROVAL; có dấu thì qua PENDING_SEAL."""
        def reach(start: str, avoid: set[str]) -> set[str]:
            seen, stack = {start}, [start]
            while stack:
                for nxt in dm.DOCUMENT_TRANSITIONS[stack.pop()]:
                    if nxt not in seen and nxt not in avoid:
                        seen.add(nxt)
                        stack.append(nxt)
            return seen
        self.assertNotIn("ISSUED", reach("DRAFT", {"PENDING_APPROVAL"}))
        self.assertIn("ISSUED", reach("DRAFT", set()))  # chính phép thử có răng: không tránh gì thì tới được

    def test_can_transition(self):
        self.assertTrue(dm.can_transition("DRAFT", "PENDING_APPROVAL"))
        for source, target in (("DRAFT", "APPROVED"), ("DRAFT", "ISSUED"), ("PENDING_APPROVAL", "ISSUED"), ("ARCHIVED", "DRAFT"), ("X", "DRAFT"), ("DRAFT", "X")):
            self.assertFalse(dm.can_transition(source, target), (source, target))


if __name__ == "__main__":
    unittest.main()
