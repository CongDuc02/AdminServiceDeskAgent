"""Test bước kiểm khởi động #10 — B2. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_checks_logging -v"""
from __future__ import annotations

import io
import logging
import unittest

from bo19.config.settings import load_settings
from bo19.observability.handler import MaskedJsonHandler
from bo19.observability.log import configure_logging
from bo19.startup.checks_logging import evaluate_root_handlers, step_10
from bo19.startup.model import Context, Entry
from pathlib import Path


def ctx() -> Context:
    return Context(Entry.API, load_settings({}), {}, None, Path("."))


class Pure(unittest.TestCase):
    def test_dung_mot_handler_mask(self):
        self.assertEqual(evaluate_root_handlers([MaskedJsonHandler(io.StringIO())]), [])

    def test_khong_co_handler(self):
        self.assertEqual(evaluate_root_handlers([]), ["STARTUP_10_ROOT_HANDLERS_NOT_ONE"])

    def test_hai_handler(self):
        self.assertEqual(evaluate_root_handlers([MaskedJsonHandler(io.StringIO()), logging.StreamHandler()]), ["STARTUP_10_ROOT_HANDLERS_NOT_ONE"])
        self.assertEqual(evaluate_root_handlers([MaskedJsonHandler(), MaskedJsonHandler()]), ["STARTUP_10_ROOT_HANDLERS_NOT_ONE"])

    def test_mot_handler_khong_phai_mask(self):
        self.assertEqual(evaluate_root_handlers([logging.StreamHandler()]), ["STARTUP_10_ROOT_HANDLER_NOT_MASK"])

    def test_lop_con_cua_handler_mask_khong_duoc_chap_nhan(self):
        class Sneaky(MaskedJsonHandler):
            pass
        self.assertEqual(evaluate_root_handlers([Sneaky()]), ["STARTUP_10_ROOT_HANDLER_NOT_MASK"])


class TrenRootLoggerThat(unittest.TestCase):
    def setUp(self):
        self.saved = list(logging.getLogger().handlers)
        self.addCleanup(self._restore)

    def _restore(self):
        root = logging.getLogger()
        for h in list(root.handlers):
            root.removeHandler(h)
        for h in self.saved:
            root.addHandler(h)

    def test_sau_configure_logging_dat(self):
        configure_logging(io.StringIO())
        self.assertEqual(step_10(ctx()).codes, ())

    def test_thu_vien_gan_them_handler_la_chan(self):
        configure_logging(io.StringIO())
        logging.getLogger().addHandler(logging.StreamHandler(io.StringIO()))  # như một thư viện gọi logging.basicConfig lúc import
        self.assertEqual(step_10(ctx()).codes, ("STARTUP_10_ROOT_HANDLERS_NOT_ONE",))

    def test_chua_cai_handler_la_chan(self):
        for h in list(logging.getLogger().handlers):
            logging.getLogger().removeHandler(h)
        self.assertEqual(step_10(ctx()).codes, ("STARTUP_10_ROOT_HANDLERS_NOT_ONE",))


if __name__ == "__main__":
    unittest.main()
