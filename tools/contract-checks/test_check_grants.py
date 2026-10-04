"""Test của bộ kiểm — parser nguồn kỳ vọng phải hỏng thành tiếng (PO, 2026-10-04).

Chạy: .venv/Scripts/python -m unittest test_check_grants -v     (Windows; Linux: .venv/bin/python)
Không cần PostgreSQL: mọi ca dừng ở bước nạp kỳ vọng, trước khi kết nối hay dựng server.
"""
import contextlib
import importlib.util
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("check_grants", HERE / "check_grants.py")
cg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cg)

REAL_DESIGN = cg.DATA_DESIGN.read_text(encoding="utf-8")
APPEND_ROW = next(l for l in REAL_DESIGN.splitlines() if l.startswith("| **Chỉ thêm** |"))


class GroupParserFailsLoudly(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="bo19-cg-test-"))
        self.saved = (cg.DATA_DESIGN, cg.MIGRATIONS, cg.SCHEMA, cg.LEDGER_FILE)
        shutil.copytree(cg.MIGRATIONS, self.tmp / "schema")
        cg.MIGRATIONS = self.tmp / "schema"

    def tearDown(self):
        cg.DATA_DESIGN, cg.MIGRATIONS, cg.SCHEMA, cg.LEDGER_FILE = self.saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def design(self, text: str) -> None:
        p = self.tmp / "04-data.md"
        p.write_text(text, encoding="utf-8")
        cg.DATA_DESIGN = p

    def run_main(self, *args: str) -> tuple[int, str]:
        out, old = io.StringIO(), sys.argv
        sys.argv = ["check_grants.py", *args]
        try:
            with contextlib.redirect_stdout(out):
                code = cg.main()
        finally:
            sys.argv = old
        return code, out.getvalue()

    # --- đối chứng: nguồn thật nạp được --------------------------------------------------
    def test_nguon_that_nap_duoc(self):
        cg.load_expectations(migrated=True)
        cg.load_expectations(migrated=False)

    # --- ca 1: một nhóm parse ra rỗng ----------------------------------------------------
    def test_nhom_rong_thoat_ma_2(self):
        empty_row = "| **Chỉ thêm** | — | Không `UPDATE`, không `DELETE` |"
        self.design(REAL_DESIGN.replace(APPEND_ROW, empty_row.replace("`UPDATE`, không `DELETE`", "UPDATE, không DELETE")))
        with self.assertRaisesRegex(cg.ExpectationError, "parse ra rỗng"):
            cg.design_groups()
        code, out = self.run_main("--local")
        self.assertEqual(code, 2)
        self.assertIn("parse ra rỗng", out)

    # --- ca 2: bảng có trong schema mà không thuộc nhóm nào ------------------------------
    def test_bang_khong_thuoc_nhom_thoat_ma_2(self):
        (cg.MIGRATIONS / "0999_bang_la.sql").write_text(
            "-- bảng thử, không có trong 04-data.md\nCREATE TABLE bang_la (id integer PRIMARY KEY);\n",
            encoding="utf-8")
        with self.assertRaisesRegex(cg.ExpectationError, "không thuộc nhóm quyền nào.*bang_la"):
            cg.validate_groups(cg.design_groups(), cg.schema_tables(sorted(cg.MIGRATIONS.glob("*.sql"))))
        code, out = self.run_main("--local-migrated")
        self.assertEqual(code, 2)
        self.assertIn("bang_la", out)

    # --- ca 3: một bảng thuộc hơn một nhóm -----------------------------------------------
    def test_bang_hai_nhom_thoat_ma_2(self):
        self.design(REAL_DESIGN.replace(APPEND_ROW, APPEND_ROW.replace("`procedure_chunk`", "`procedure_chunk`, `job`")))
        with self.assertRaisesRegex(cg.ExpectationError, "job thuộc hơn một nhóm"):
            cg.validate_groups(cg.design_groups(), cg.schema_tables([cg.SCHEMA]))
        code, out = self.run_main("--local")
        self.assertEqual(code, 2)
        self.assertIn("thuộc hơn một nhóm", out)

    # --- sổ migration: đọc từ file DDL sổ, bo19_app chỉ SELECT (PO, 2026-10-04) ----------
    def ledger(self, text: str) -> None:
        p = self.tmp / "schema_migration.sql"
        p.write_text(text, encoding="utf-8")
        cg.LEDGER_FILE = p

    def test_so_doc_tu_file(self):
        self.assertEqual(cg.ledger_tables(), ["schema_migration"])

    def test_so_cap_them_quyen_ghi_thoat_ma_2(self):
        real = self.saved[3].read_text(encoding="utf-8")
        self.ledger(real.replace("GRANT SELECT ON schema_migration", "GRANT SELECT, INSERT ON schema_migration"))
        with self.assertRaisesRegex(cg.ExpectationError, "phải đúng SELECT"):
            cg.ledger_tables()
        code, out = self.run_main("--local")
        self.assertEqual(code, 2)
        self.assertIn("phải đúng SELECT", out)

    def test_so_rong_thoat_ma_2(self):
        self.ledger("-- chỉ chú thích\n")
        code, out = self.run_main("--local")
        self.assertEqual(code, 2)
        self.assertIn("không có câu SQL thực thi được", out)

    # --- chú thích không tính là bảng ----------------------------------------------------
    def test_create_table_trong_chu_thich_khong_tinh(self):
        f = self.tmp / "x.sql"
        f.write_text("-- CREATE TABLE ma (id int);\n/* CREATE TABLE ma2 (id int); */\nCREATE TABLE that (id int);\n",
                     encoding="utf-8")
        self.assertEqual(cg.schema_tables([f]), {"that"})


if __name__ == "__main__":
    unittest.main()
