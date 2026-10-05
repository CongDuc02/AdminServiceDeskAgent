"""Test bước kiểm khởi động #12, #19 và #20 — B2.

Tên biến tracing ở #19 KHÔNG lấy từ trí nhớ: chúng đến từ `docs/reference/langsmith-tracing-env-nguon-goc.md` (nguồn gốc tải bằng `curl`, đúng
bản lock: langsmith 0.14.3, langchain-core 1.6.6). Test dưới đây (1) phủ từng tên của các mục tài liệu đó, và (2) đọc lại chính file tài liệu,
rút mọi tên `LANGSMITH_*`/`LANGCHAIN_*` có `TRACING` rồi đòi bước kiểm bắt từng tên — để một tên mới ghi vào tài liệu không lọt qua test.

Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_checks_security -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import io
import json
import logging
import re
import unittest
from pathlib import Path

from bo19.config.settings import load_settings
from bo19.observability.log import configure_logging
from bo19.startup import runner
from bo19.startup.checks_security import step_12, step_19, step_20, tracing_variable_names
from bo19.startup.model import Context, Entry

REFERENCE = Path(__file__).resolve().parents[2] / "docs" / "reference" / "langsmith-tracing-env-nguon-goc.md"
BASE = {"BO19_ENVIRONMENT": "dev", "BO19_DATABASE_URL": "x", "BO19_SESSION_SECRET": "y" * 32}

# Mục 1 của tài liệu — bốn tên bật tracing (N1, `tracing_is_enabled`, hai tiền tố × hai tên).
DOC_S1_ENABLING = ("LANGSMITH_TRACING_V2", "LANGCHAIN_TRACING_V2", "LANGSMITH_TRACING", "LANGCHAIN_TRACING")
# Mục 2 — tên trong tài liệu sản phẩm (N5, N6).
DOC_S2_PRODUCT_DOC = ("LANGSMITH_TRACING",)
# Mục 3 — tên có TRACING nhưng không tự bật (N2, `client.py`), mỗi tên hai tiền tố.
DOC_S3_CONFIG = ("LANGSMITH_TRACING_MODE", "LANGCHAIN_TRACING_MODE", "LANGSMITH_TRACING_SAMPLING_RATE", "LANGCHAIN_TRACING_SAMPLING_RATE",
                 "LANGSMITH_TRACING_QUEUE_MAX_SIZE", "LANGCHAIN_TRACING_QUEUE_MAX_SIZE")
# Mục 4 — liên quan OpenTelemetry, không chứa TRACING.
DOC_S4_OTEL = ("LANGSMITH_OTEL_ENABLED", "LANGSMITH_OTEL_ONLY", "LANGCHAIN_OTEL_ENABLED", "LANGCHAIN_OTEL_ONLY")
EVERY_TRACING_NAME = sorted(set(DOC_S1_ENABLING + DOC_S2_PRODUCT_DOC + DOC_S3_CONFIG))


def ctx(env: dict, entry: Entry = Entry.API, **config) -> Context:
    return Context(entry, load_settings({**BASE, **config}), env, None, Path("."))


class Buoc19(unittest.TestCase):
    def test_moi_ten_trong_tai_lieu_bi_chan_voi_moi_kieu_gia_tri(self):
        for name in EVERY_TRACING_NAME:
            for value in ("true", "True", "false", "0", "1", "", "   ", "BI_MAT_GIA_TRI"):  # bất kể giá trị, kể cả rỗng
                got = step_19(ctx({name: value})).codes
                self.assertEqual(got, (f"STARTUP_19_TRACING_ENV_SET:{name}",), (name, value))

    def test_khong_phan_biet_hoa_thuong(self):
        for name in EVERY_TRACING_NAME:
            for variant in (name.lower(), name.title(), name.swapcase()):
                self.assertEqual(len(step_19(ctx({variant: "true"})).codes), 1, variant)

    def test_gia_tri_khong_bao_gio_vao_ma(self):
        got = step_19(ctx({"LANGSMITH_TRACING": "BI_MAT_GIA_TRI"})).codes
        self.assertNotIn("BI_MAT_GIA_TRI", "".join(got))

    def test_nhieu_bien_cung_luc_duoc_liet_ke_het_theo_thu_tu_ten(self):
        env = {"LANGCHAIN_TRACING_V2": "true", "LANGSMITH_TRACING": "", "PATH": "/bin"}
        self.assertEqual(step_19(ctx(env)).codes, ("STARTUP_19_TRACING_ENV_SET:LANGCHAIN_TRACING_V2", "STARTUP_19_TRACING_ENV_SET:LANGSMITH_TRACING"))

    def test_moi_truong_sach_dat(self):
        self.assertEqual(step_19(ctx({})).codes, ())
        self.assertEqual(step_19(ctx({"PATH": "/bin", "BO19_ENVIRONMENT": "dev"})).codes, ())

    def test_bien_langsmith_khac_khong_bi_chan(self):
        """Chỉ mẫu `*_TRACING*`; khoá API, tên project, endpoint không bật tracing nếu không có biến bật (langsmith-tracing-env.md mục 2, mục 4)."""
        for name in ("LANGSMITH_API_KEY", "LANGSMITH_PROJECT", "LANGCHAIN_PROJECT", "LANGSMITH_ENDPOINT", "LANGCHAIN_CALLBACKS_BACKGROUND",
                     "LANGSMITH_WORKSPACE_ID"):
            self.assertEqual(step_19(ctx({name: "x"})).codes, (), name)

    def test_ten_otel_trong_tai_lieu_khong_chua_tracing_nen_mau_khong_bat(self):
        """Ghi lại đúng hành vi của đặc tả #19: hai tên OTel chỉ chọn nơi gửi khi tracing ĐÃ bật (tài liệu mục 4), không chứa `TRACING` — mẫu không bắt.
        Muốn bắt chúng phải sửa mẫu ở đặc tả #19 trước, rồi sửa test này."""
        for name in DOC_S4_OTEL:
            self.assertEqual(step_19(ctx({name: "true"})).codes, (), name)

    def test_chua_dung_tien_to_hoac_khong_co_tracing_thi_khong_bat(self):
        for name in ("MY_LANGSMITH_TRACING", "TRACING", "LANGSMITH", "LANGSMITHTRACING", "LANGSMITH_TRACE", "XLANGCHAIN_TRACING_V2", "LANG_SMITH_TRACING"):
            self.assertEqual(step_19(ctx({name: "true"})).codes, (), name)

    def test_ten_la_duoc_lam_sach_truoc_khi_vao_ma(self):
        got = tracing_variable_names({"LANGSMITH_TRACING\nINJECT": "x", "LANGSMITH_TRACING" + "A" * 200: "x"})
        self.assertTrue(all(re.fullmatch(r"[A-Za-z0-9_?]{1,80}", n) for n in got), got)

    def test_chay_o_ca_ba_entrypoint(self):
        for entry in (Entry.API, Entry.WORKER, Entry.CRON):
            self.assertEqual(len(step_19(ctx({"LANGSMITH_TRACING": "true"}, entry)).codes), 1, entry)

    def test_qua_bo_chay_gia_tri_khong_lo_ra_log(self):
        out = io.StringIO()
        h = configure_logging(out)
        self.addCleanup(logging.getLogger().removeHandler, h)
        env = {**BASE, "LANGSMITH_TRACING": "BI_MAT_GIA_TRI"}
        report = runner.run(Entry.CRON, load_settings(env), env, registry={"19": step_19}, connector=lambda d, a: None)
        self.assertEqual(report.failures, ("STARTUP_19_TRACING_ENV_SET:LANGSMITH_TRACING",))
        self.assertNotIn("BI_MAT_GIA_TRI", out.getvalue())
        logged = [json.loads(x)["code"] for x in out.getvalue().splitlines() if '"STARTUP_FAIL"' in x]
        self.assertEqual(logged, list(report.failures))


@unittest.skipUnless(REFERENCE.exists(), "không có docs/ cạnh test")
class Buoc19TuTaiLieu(unittest.TestCase):
    """Đọc lại tài liệu gốc đã lưu: mọi tên `*TRACING*` trong đó phải bị bắt; và danh sách cứng ở trên phải có mặt trong tài liệu."""

    @classmethod
    def setUpClass(cls):
        text = REFERENCE.read_text(encoding="utf-8")
        cls.names = set(re.findall(r"`((?:LANGSMITH|LANGCHAIN)_[A-Z0-9_]*[A-Z0-9])`", text))

    def test_danh_sach_cung_nam_trong_tai_lieu(self):
        for name in DOC_S1_ENABLING + DOC_S3_CONFIG:
            self.assertIn(name, self.names, f"{name} không có trong tài liệu — danh sách cứng của test lệch tài liệu")

    def test_moi_ten_co_tracing_trong_tai_lieu_bi_bat(self):
        tracing = {n for n in self.names if "TRACING" in n}
        self.assertGreaterEqual(len(tracing), 10)
        for name in sorted(tracing):
            self.assertEqual(len(step_19(ctx({name: ""})).codes), 1, f"{name} có trong tài liệu nhưng #19 không bắt")

    def test_ten_khong_co_tracing_trong_tai_lieu_khong_bi_bat_nham(self):
        for name in sorted(n for n in self.names if "TRACING" not in n):
            self.assertEqual(step_19(ctx({name: "x"})).codes, (), name)


class Buoc12(unittest.TestCase):
    def test_co_mat_la_dat(self):
        self.assertEqual(step_12(ctx({})).codes, ())

    def test_thieu_hoac_rong_la_chan(self):
        for env in ({"BO19_SESSION_SECRET": ""}, {"BO19_SESSION_SECRET": "   "}):
            c = Context(Entry.API, load_settings({**BASE, **env}), {}, None, Path("."))
            self.assertEqual(step_12(c).codes, ("STARTUP_12_SESSION_SECRET_MISSING",))
        c = Context(Entry.API, load_settings({k: v for k, v in BASE.items() if k != "BO19_SESSION_SECRET"}), {}, None, Path("."))
        self.assertEqual(step_12(c).codes, ("STARTUP_12_SESSION_SECRET_MISSING",))

    def secret(self, value: str):
        return step_12(Context(Entry.API, load_settings({**BASE, "BO19_SESSION_SECRET": value}), {}, None, Path("."))).codes

    def test_ngan_hon_32_byte_la_chan(self):  # A-088: HS256 — docs/reference/pyjwt-hmac-key-length.md
        for n in (1, 16, 31):
            self.assertEqual(self.secret("x" * n), ("STARTUP_12_SESSION_SECRET_TOO_SHORT",), n)

    def test_tu_32_byte_tro_len_la_dat(self):
        for n in (32, 33, 64, 200):
            self.assertEqual(self.secret("x" * n), (), n)

    def test_do_dai_do_bang_byte_khong_phai_ky_tu(self):
        self.assertEqual(self.secret("é" * 16), ())  # 16 ký tự, 32 byte UTF-8
        self.assertEqual(self.secret("é" * 15), ("STARTUP_12_SESSION_SECRET_TOO_SHORT",))  # 15 ký tự, 30 byte
        self.assertEqual(self.secret("x" * 31 + "é"), ())  # 32 ký tự, 33 byte

    def test_khoang_trang_hai_dau_khong_duoc_tinh_vao_do_dai(self):
        self.assertEqual(self.secret("  " + "x" * 31 + "  "), ("STARTUP_12_SESSION_SECRET_TOO_SHORT",))  # settings cắt khoảng trắng trước khi dùng làm khoá

    def test_ma_truot_khong_lo_gia_tri_secret(self):
        for code_ in self.secret("BI_MAT_NGAN"):
            self.assertNotIn("BI_MAT_NGAN", code_)


class Buoc20(unittest.TestCase):
    """WV-16: time_cost ≥ 2, memory_cost ≥ 19456 KiB, parallelism = 1. Không ngoại lệ theo môi trường."""

    def run20(self, **config):
        return step_20(ctx({}, **config)).codes

    def test_mac_dinh_dat(self):
        self.assertEqual(self.run20(), ())

    def test_ranh_gioi_tung_tham_so(self):
        self.assertEqual(self.run20(BO19_ARGON2_TIME_COST="2"), ())
        self.assertEqual(self.run20(BO19_ARGON2_TIME_COST="1"), ("STARTUP_20_ARGON2_TIME_COST_BELOW_MIN",))
        self.assertEqual(self.run20(BO19_ARGON2_MEMORY_COST_KIB="19456"), ())
        self.assertEqual(self.run20(BO19_ARGON2_MEMORY_COST_KIB="19455"), ("STARTUP_20_ARGON2_MEMORY_COST_KIB_BELOW_MIN",))
        self.assertEqual(self.run20(BO19_ARGON2_PARALLELISM="1"), ())
        self.assertEqual(self.run20(BO19_ARGON2_PARALLELISM="2"), ("STARTUP_20_ARGON2_PARALLELISM_NOT_1",))

    def test_cao_hon_toi_thieu_la_dat(self):
        self.assertEqual(self.run20(BO19_ARGON2_TIME_COST="3", BO19_ARGON2_MEMORY_COST_KIB="65536"), ())

    def test_nhieu_tham_so_thap_cung_luc_gom_het(self):
        got = self.run20(BO19_ARGON2_TIME_COST="1", BO19_ARGON2_MEMORY_COST_KIB="1024", BO19_ARGON2_PARALLELISM="4")
        self.assertEqual(got, ("STARTUP_20_ARGON2_TIME_COST_BELOW_MIN", "STARTUP_20_ARGON2_MEMORY_COST_KIB_BELOW_MIN", "STARTUP_20_ARGON2_PARALLELISM_NOT_1"))

    def test_khong_ngoai_le_theo_moi_truong(self):
        for environment in ("dev", "staging", "prod"):
            c = Context(Entry.API, load_settings({**BASE, "BO19_ENVIRONMENT": environment, "BO19_ARGON2_TIME_COST": "1"}), {}, None, Path("."))
            self.assertEqual(step_20(c).codes, ("STARTUP_20_ARGON2_TIME_COST_BELOW_MIN",), environment)

    def test_gia_tri_khong_hop_le_la_ma_rieng(self):
        self.assertEqual(self.run20(BO19_ARGON2_TIME_COST="abc"), ("STARTUP_20_ARGON2_TIME_COST_INVALID",))
        self.assertEqual(self.run20(BO19_ARGON2_MEMORY_COST_KIB="0"), ("STARTUP_20_ARGON2_MEMORY_COST_KIB_INVALID",))


if __name__ == "__main__":
    unittest.main()
