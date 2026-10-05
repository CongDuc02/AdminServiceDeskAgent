"""Test các contract của .importlinter — mỗi contract phải có thật sự chặn. AC-1.12 ở dạng test; CI còn chứng minh bằng một nhánh bỏ đi.

Chạy từ backend/:  python -m unittest tests.test_import_contracts -v     (cần import-linter — requirements-dev-linux.lock)
Không có import-linter thì bỏ qua cả lớp (image chạy không có công cụ dev). Mỗi ca chép src/ và .importlinter vào thư mục tạm, thêm một
file vi phạm rồi chạy `lint-imports`: mã thoát 1 và đúng contract bị phá. Ca "sạch" và ca "gián tiếp hợp lệ" phải đạt (mã 0).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def have_linter() -> bool:
    return subprocess.run([sys.executable, "-m", "importlinter.cli", "--version"], capture_output=True).returncode == 0 or shutil.which("lint-imports") is not None


@unittest.skipUnless(have_linter(), "import-linter chưa cài (requirements-dev-linux.lock)")
class Contracts(unittest.TestCase):
    def lint(self, add: dict[str, str]) -> tuple[int, str]:
        """Chép src/ + .importlinter, thêm các file `add` (đường dẫn tương đối src/bo19/... → nội dung), chạy lint-imports."""
        with tempfile.TemporaryDirectory() as d:
            w = Path(d)
            shutil.copytree(BACKEND / "src", w / "src", ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copy(BACKEND / ".importlinter", w / ".importlinter")
            for rel, text in add.items():
                f = w / "src" / "bo19" / rel
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(text, encoding="utf-8")
            r = subprocess.run(["lint-imports", "--no-cache", "--no-logo"], cwd=w, env={"PYTHONPATH": "src", "PATH": __import__("os").environ["PATH"]},
                               capture_output=True, text=True, encoding="utf-8")
            return r.returncode, r.stdout + r.stderr

    def broken(self, out: str) -> list[str]:
        """Tên các contract bị phá — dòng kết thúc bằng BROKEN (tên dài có thể xuống dòng; ghép lại)."""
        flat = " ".join(out.split())
        return [n for n in ("Tầng — chỉ import xuống", "ai_gateway và tool_layer độc lập", "api chỉ vào orchestrator", "Lối ghi DB", "Chỉ bước kiểm khởi động dùng lối thử quyền",
                            "Chỉ tool_layer.storage chạm object_storage", "Đường tới provider đi qua gateway", "LangGraph chỉ ở orchestrator.runtime") if f"{n}" in flat and flat.count("BROKEN") and self._is_broken(flat, n)]

    @staticmethod
    def _is_broken(flat: str, name: str) -> bool:
        i = flat.find(name)
        j = flat.find("KEPT", i)
        k = flat.find("BROKEN", i)
        return k != -1 and (j == -1 or k < j)

    def test_sach_dat(self):
        rc, out = self.lint({})
        self.assertEqual(rc, 0, out)
        self.assertIn("8 kept, 0 broken", out)

    def test_import_gian_tiep_hop_le_van_dat(self):
        # api → orchestrator.runner → ai_gateway: chuỗi hợp lệ, không được tính là api chạm ai_gateway (allow_indirect_imports)
        rc, out = self.lint({"api/routers/ok.py": "import bo19.orchestrator.runner\n", "orchestrator/runner.py": "import bo19.ai_gateway.gateway\n"})
        self.assertEqual(rc, 0, out)

    def test_tang_import_nguoc_len(self):
        rc, out = self.lint({"persistence/up.py": "import bo19.api.app\n"})
        self.assertEqual(rc, 1, out)
        self.assertIn("Tầng — chỉ import xuống", self.broken(out))

    def test_api_import_thang_ai_gateway(self):
        rc, out = self.lint({"api/routers/bad.py": "import bo19.ai_gateway.gateway\n"})
        self.assertEqual(rc, 1, out)
        self.assertIn("api chỉ vào orchestrator", self.broken(out))

    def test_api_import_thang_loi_ghi(self):
        rc, out = self.lint({"api/routers/bad.py": "import bo19.persistence.write\n"})
        self.assertEqual(rc, 1, out)
        self.assertTrue({"api chỉ vào orchestrator", "Lối ghi DB"} & set(self.broken(out)), out)

    def test_loi_probe_chi_cho_buoc_kiem_khoi_dong(self):
        rc, out = self.lint({"tool_layer/kernel/p.py": "import bo19.persistence.probe\n"})
        self.assertEqual(rc, 1, out)
        self.assertIn("Chỉ bước kiểm khởi động dùng lối thử quyền", self.broken(out))

    def test_object_storage_chi_tool_layer_storage(self):
        rc, out = self.lint({"tool_layer/jobs/s.py": "import bo19.object_storage\n"})
        self.assertEqual(rc, 1, out)
        self.assertIn("Chỉ tool_layer.storage chạm object_storage", self.broken(out))

    def test_httpx_ngoai_gateway(self):
        rc, out = self.lint({"tool_layer/kernel/h.py": "import httpx\n"})
        self.assertEqual(rc, 1, out)
        self.assertIn("Đường tới provider đi qua gateway", self.broken(out))

    def test_langgraph_ngoai_runtime(self):
        rc, out = self.lint({"api/routers/lg.py": "import langgraph\n"})
        self.assertEqual(rc, 1, out)
        self.assertIn("LangGraph chỉ ở orchestrator.runtime", self.broken(out))

    def test_api_va_queue_worker_doc_lap(self):
        # cùng tầng, ngăn cách bằng `|` — không được import lẫn nhau (tài liệu 2.15: "independent" khi dùng dấu gạch đứng)
        for add in ({"queue_worker/h.py": "import bo19.api\n"}, {"api/h.py": "import bo19.queue_worker\n"}):
            rc, out = self.lint(add)
            self.assertEqual(rc, 1, (add, out))
            self.assertIn("Tầng — chỉ import xuống", self.broken(out))

    def test_object_storage_va_persistence_doc_lap(self):
        rc, out = self.lint({"persistence/o.py": "import bo19.object_storage\n"})
        self.assertEqual(rc, 1, out)
        self.assertIn("Tầng — chỉ import xuống", self.broken(out))

    def test_ai_gateway_va_tool_layer_doc_lap(self):
        rc, out = self.lint({"tool_layer/kernel/s.py": "import bo19.ai_gateway\n"})
        self.assertEqual(rc, 1, out)
        self.assertIn("ai_gateway và tool_layer độc lập", self.broken(out))


if __name__ == "__main__":
    unittest.main()
