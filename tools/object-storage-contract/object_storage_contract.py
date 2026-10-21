"""Phép thử hợp đồng object storage THẬT — bước S7 của Spike 1, cổng 2.5 (A-024, ADR-037 điều kiện 3). KHÔNG phải mã ứng dụng, không vào image.

Chạy bộ phép thử qua ĐÚNG adapter của dự án (`bo19.object_storage.ObjectStorage`: SigV4, path-style, `If-None-Match: *` trên mọi PUT): ghi một lần (412 và byte cũ nguyên), tám luồng cùng một khoá (một thắng),
metadata trong cùng lệnh PUT, GET/HEAD/LIST/DELETE, đọc theo khối, ánh xạ lỗi khi sai credential. Cách chạy, luật, danh sách việc: tools/object-storage-contract/README.md.

Luật (PO, 2026-10-21):
  - cấu hình CHỈ từ năm biến môi trường BO19_OBJECT_STORAGE_* do người chạy export tường minh — tool KHÔNG đọc `.env` hay file nào; credential không trên dòng lệnh, không in, không ghi;
  - CHỈ gọi mạng thật khi có `--confirm-real` (không có thì in kế hoạch, mã thoát 3);
  - CHỈ đụng khoá dưới tiền tố `s7-probe/<mã lần chạy>/`; xong thì dọn và kiểm bucket không còn khoá nào của lần chạy; không bao giờ liệt kê hay xoá khoá ngoài tiền tố đó;
  - chỉ ghi số, mã và kết quả đạt/không — không ghi endpoint (có mã tài khoản), tên bucket, khoá; `self_check` quét kết quả trước khi ghi, không đạt thì không ghi file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend" / "src"))

import boto3  # noqa: E402 — chỉ để chẩn đoán mã lỗi gốc của một lệnh bị từ chối (tool không thuộc contract `object-storage`)
import botocore  # noqa: E402
from botocore.config import Config  # noqa: E402
from botocore.exceptions import BotoCoreError, ClientError  # noqa: E402

from bo19.object_storage import (  # noqa: E402
    ALREADY_EXISTS, OBJECT_MISSING, AlreadyExists, ObjectMissing, ObjectStorage, ObjectStorageConfig, StorageError)

PREFIX_ROOT = "s7-probe/"
THREADS = 8
ENV_NAMES = ("BO19_OBJECT_STORAGE_ENDPOINT_URL", "BO19_OBJECT_STORAGE_BUCKET", "BO19_OBJECT_STORAGE_REGION", "BO19_OBJECT_STORAGE_ACCESS_KEY_ID", "BO19_OBJECT_STORAGE_SECRET_ACCESS_KEY")
OUT = Path(__file__).resolve().parent / "out"
REFERENCE_DIR = REPO / "docs" / "reference"
NOT_RUN = (
    ("PutBucketVersioning / GetBucketVersioning", "token Object Read & Write không có quyền cấu hình bucket; bảng tương thích của nhà cung cấp ghi chưa hỗ trợ — xem docs/reference/r2-s3-endpoint-va-region.md"),
    ("PutObjectLockConfiguration / PutObjectRetention", "như trên; A-024 chỉ đòi MỘT trong ba lớp bảo vệ, lớp đã chọn là ghi có điều kiện (ADR-037)"),
)


@dataclass
class Check:
    id: str
    title: str
    required: bool = True
    ok: bool | None = None
    ms: int | None = None
    facts: dict[str, Any] = field(default_factory=dict)


@dataclass
class Settings:
    endpoint_url: str
    bucket: str
    region: str
    access_key_id: str
    secret_access_key: str

    def secrets(self) -> list[str]:
        host = self.endpoint_url.split("://", 1)[-1].split("/", 1)[0]
        return [self.endpoint_url, host, host.split(".", 1)[0], self.bucket, self.access_key_id, self.secret_access_key]

    def storage(self, *, secret: str | None = None) -> ObjectStorage:
        return ObjectStorage(ObjectStorageConfig(endpoint_url=self.endpoint_url, bucket=self.bucket, access_key_id=self.access_key_id,
                                                 secret_access_key=secret or self.secret_access_key, region=self.region, timeout_s=30))


def read_settings(environ: dict[str, str] | None = None) -> tuple[Settings | None, list[str]]:
    env = os.environ if environ is None else environ
    missing = [n for n in ENV_NAMES if not env.get(n)]
    if missing:
        return None, missing
    return Settings(*(env[n] for n in ENV_NAMES)), []


def _raw_put_diagnosis(s: Settings, key: str) -> dict[str, Any]:
    """Một PUT có điều kiện lên khoá ĐÃ CÓ bằng client trần — chỉ lấy mã HTTP và `Error.Code` (chuỗi ngắn, chỉ chữ) để biết sản phẩm trả gì khi adapter báo `STORAGE_UNAVAILABLE`."""
    client = boto3.client("s3", endpoint_url=s.endpoint_url, region_name=s.region, aws_access_key_id=s.access_key_id, aws_secret_access_key=s.secret_access_key,
                          config=Config(signature_version="s3v4", s3={"addressing_style": "path"}, retries={"max_attempts": 1}, connect_timeout=30, read_timeout=30))
    try:
        client.put_object(Bucket=s.bucket, Key=key, Body=b"diagnosis", IfNoneMatch="*")
        return {"http_status": 200}
    except ClientError as e:
        code = str(e.response.get("Error", {}).get("Code", ""))
        return {"http_status": int(e.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0) or 0), "error_code": code if code.isalnum() and len(code) <= 64 else "?"}
    except BotoCoreError as e:
        return {"client_error": type(e).__name__}


class Suite:
    def __init__(self, settings: Settings, run_id: str) -> None:
        self.s = settings
        self.storage = settings.storage()
        self.prefix = f"{PREFIX_ROOT}{run_id}/"
        self.written: list[str] = []
        self.checks: list[Check] = []

    def key(self, name: str) -> str:
        k = f"{self.prefix}{name}"
        assert k.startswith(PREFIX_ROOT)
        return k

    def _run(self, check: Check, fn: Callable[[Check], bool]) -> None:
        t0 = time.monotonic()
        try:
            check.ok = bool(fn(check))
        except StorageError as e:
            check.ok, check.facts["storage_error"] = False, e.code
        except Exception as e:  # noqa: BLE001 — một phép thử hỏng không được làm mất kết quả các phép thử còn lại
            check.ok, check.facts["exception"] = False, type(e).__name__
        check.ms = round((time.monotonic() - t0) * 1000)
        self.checks.append(check)

    # ---- các phép thử -----------------------------------------------------------------------------------------------------------
    def c0_reachable(self, c: Check) -> bool:
        c.facts["head_bucket"] = self.storage.reachable()
        return True  # thông tin: token giới hạn theo bucket có thể không có quyền HeadBucket — adapter dùng nó ở bước kiểm khởi động #14

    def c1_put_new(self, c: Check) -> bool:
        k = self.key("t1")
        self.written.append(k)
        self.storage.put_if_absent(k, b"ban-dau", content_type="text/plain")
        return self.storage.get(k) == b"ban-dau"

    def c2_put_again_412(self, c: Check) -> bool:
        k = self.key("t2")
        self.written.append(k)
        self.storage.put_if_absent(k, b"ban-dau", content_type="text/plain")
        try:
            self.storage.put_if_absent(k, b"ban-moi-khac-byte", content_type="text/plain")
            c.facts["second_put"] = "ACCEPTED"
            return False
        except AlreadyExists:
            c.facts["second_put"] = ALREADY_EXISTS
        c.facts["old_bytes_intact"] = self.storage.get(k) == b"ban-dau"
        return c.facts["old_bytes_intact"]

    def c3_metadata(self, c: Check) -> bool:
        k = self.key("t3")
        self.written.append(k)
        meta = {"bo19-document-number": "TRIAL-0001", "bo19-pin-reason": "ISSUED"}
        self.storage.put_if_absent(k, b"x" * 2048, content_type="application/pdf", metadata=meta)
        info = self.storage.head(k)
        c.facts["metadata_roundtrip"] = info is not None and {a.lower(): b for a, b in info.metadata.items()} == meta
        c.facts["size_bytes"] = info.size_bytes if info else None
        return bool(c.facts["metadata_roundtrip"] and info and info.size_bytes == 2048)

    def c4_concurrent(self, c: Check) -> bool:
        k = self.key("t4")
        self.written.append(k)
        outcomes: list[str] = []
        lock, barrier = threading.Lock(), threading.Barrier(THREADS)

        def worker(i: int) -> None:
            barrier.wait()
            try:
                self.storage.put_if_absent(k, f"nguoi-ghi-{i}".encode(), content_type="text/plain")
                out = "OK"
            except StorageError as e:
                out = e.code
            with lock:
                outcomes.append(out)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(THREADS)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        c.facts.update(threads=THREADS, succeeded=outcomes.count("OK"), already_exists=outcomes.count(ALREADY_EXISTS),
                       other_codes=sorted({o for o in outcomes if o not in ("OK", ALREADY_EXISTS)}))
        if c.facts["other_codes"]:
            c.facts["raw_rejection"] = _raw_put_diagnosis(self.s, k)
        winner = self.storage.get(k)
        c.facts["final_object_is_one_writer"] = winner in {f"nguoi-ghi-{i}".encode() for i in range(THREADS)}
        return c.facts["succeeded"] == 1 and c.facts["already_exists"] == THREADS - 1 and c.facts["final_object_is_one_writer"]

    def c5_list(self, c: Check) -> bool:
        listed = sorted(k for k, _ in self.storage.list_keys(self.prefix) if k.startswith(self.prefix))
        c.facts.update(written=len(self.written), listed=len(listed), same_set=listed == sorted(self.written))
        return c.facts["same_set"]

    def c6_stream(self, c: Check) -> bool:
        k = self.key("t6")
        self.written.append(k)
        data = bytes(range(256)) * 1200  # 300 KiB
        self.storage.put_if_absent(k, data, content_type="application/octet-stream")
        chunks = list(self.storage.get_chunks(k, 64 * 1024))
        c.facts.update(chunks=len(chunks), bytes_equal=b"".join(chunks) == data)
        return c.facts["bytes_equal"] and len(chunks) >= 2

    def c7_missing(self, c: Check) -> bool:
        k = self.key("khong-co")
        c.facts["head_missing_is_none"] = self.storage.head(k) is None
        try:
            self.storage.get(k)
            c.facts["get_missing"] = "FOUND"
        except ObjectMissing:
            c.facts["get_missing"] = OBJECT_MISSING
        self.storage.delete(k)  # xoá khoá không có: không lỗi
        c.facts["delete_missing_ok"] = True
        return c.facts["head_missing_is_none"] and c.facts["get_missing"] == OBJECT_MISSING

    def c8_delete_then_reput(self, c: Check) -> bool:
        k = self.key("t8")
        self.written.append(k)
        self.storage.put_if_absent(k, b"mot", content_type="text/plain")
        self.storage.delete(k)
        c.facts["gone_after_delete"] = self.storage.head(k) is None
        self.storage.put_if_absent(k, b"hai", content_type="text/plain")  # xoá rồi thì ghi lại được (đường dọn object mồ côi của object_claim_reconcile)
        c.facts["reput_after_delete"] = self.storage.get(k) == b"hai"
        return c.facts["gone_after_delete"] and c.facts["reput_after_delete"]

    def c9_bad_credential(self, c: Check) -> bool:
        bad = self.s.storage(secret="khong-phai-khoa-that-" + uuid.uuid4().hex)
        try:
            bad.put_if_absent(self.key("t9"), b"x", content_type="text/plain")
            c.facts["bad_secret"] = "ACCEPTED"
            self.written.append(self.key("t9"))
            return False
        except StorageError as e:
            c.facts["bad_secret"] = e.code
            return e.code == "ACCESS_DENIED"

    def run_all(self) -> None:
        plan = (("C0", "HeadBucket với credential này (thông tin, bước kiểm khởi động #14)", False, self.c0_reachable),
                ("C1", "PUT khoá mới kèm If-None-Match: * rồi GET", True, self.c1_put_new),
                ("C2", "PUT lại khoá đã có → từ chối (412) và byte cũ nguyên (A-024, ADR-037 điều kiện 3; T2)", True, self.c2_put_again_412),
                ("C3", "Metadata và Content-Length trong cùng lệnh PUT (T3)", True, self.c3_metadata),
                ("C4", f"{THREADS} luồng cùng PUT một khoá mới → đúng một thắng (T6)", True, self.c4_concurrent),
                ("C5", "ListObjectsV2 theo tiền tố trả đúng tập khoá đã ghi (T7)", True, self.c5_list),
                ("C6", "GET theo khối 64 KiB, byte khớp", True, self.c6_stream),
                ("C7", "Khoá không có: HEAD → None, GET → OBJECT_MISSING, DELETE không lỗi", True, self.c7_missing),
                ("C8", "DELETE rồi PUT lại có điều kiện được", True, self.c8_delete_then_reput),
                ("C9", "Sai secret → ACCESS_DENIED (ánh xạ lỗi của adapter)", True, self.c9_bad_credential))
        for cid, title, required, fn in plan:
            self._run(Check(cid, title, required), fn)

    # ---- dọn ------------------------------------------------------------------------------------------------------------------
    def cleanup(self) -> dict[str, Any]:
        deleted = failed = 0
        try:
            for k in [k for k, _ in self.storage.list_keys(self.prefix) if k.startswith(self.prefix)]:
                try:
                    self.storage.delete(k)
                    deleted += 1
                except StorageError:
                    failed += 1
            left = [k for k, _ in self.storage.list_keys(self.prefix) if k.startswith(self.prefix)]
        except StorageError as e:
            return {"deleted": deleted, "failed": failed, "left": None, "error": e.code}
        return {"deleted": deleted, "failed": failed, "left": len(left)}


def self_check(text: str, secrets: list[str]) -> list[str]:
    problems = []
    for i, s in enumerate(secrets):
        if s and s in text:
            problems.append(f"SECRET_{i}_PRESENT")
    if "r2.cloudflarestorage.com" in text:
        problems.append("ENDPOINT_HOST")
    return problems


def render_markdown(label: str, settings: Settings, run_id: str, started: str, checks: list[Check], cleanup: dict[str, Any]) -> str:
    rows = "\n".join(f"| {c.id} | {c.title} | {'đạt' if c.ok else 'KHÔNG ĐẠT'}{'' if c.required else ' (thông tin)'} | {c.ms} | `{json.dumps(c.facts, ensure_ascii=False, sort_keys=True)}` |" for c in checks)
    skipped = "\n".join(f"- **{name}** — không chạy: {why}" for name, why in NOT_RUN)
    return f"""# Phép thử object storage thật — {label} (S7, cổng 2.5)

- **Sinh bằng** `tools/object-storage-contract/object_storage_contract.py --label {label}`, lần chạy `{run_id}`, bắt đầu {started} (UTC). Chỉ số, mã và kết quả; không có endpoint, tên bucket hay khoá (tool tự quét trước khi ghi).
- **Client:** `boto3` {boto3.__version__}, `botocore` {botocore.__version__}; qua adapter `bo19.object_storage.ObjectStorage` (SigV4, path-style, `retries.max_attempts = 1`). `region` = `{settings.region}`.
- **Tiền tố khoá:** chỉ `{PREFIX_ROOT}{run_id}/`. **Dọn:** xoá {cleanup.get('deleted')} khoá, lỗi {cleanup.get('failed')}, còn lại dưới tiền tố {cleanup.get('left')}.

| # | Phép thử | Kết quả | ms | Dữ kiện |
|---|---|---|---|---|
{rows}

## Không chạy

{skipped}
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Phép thử hợp đồng object storage thật — S7 (tools/object-storage-contract/README.md)")
    ap.add_argument("--confirm-real", action="store_true", help="BẮT BUỘC để gọi mạng thật. Không có cờ này tool chỉ in kế hoạch rồi thoát (mã 3)")
    ap.add_argument("--label", default="r2", help="tên nhà cung cấp trong tên file kết quả (chữ thường, số, gạch ngang)")
    ap.add_argument("--no-publish", action="store_true", help="chỉ ghi out/, không ghi docs/reference/")
    ap.add_argument("--out-dir", type=Path, default=OUT)
    ap.add_argument("--reference-dir", type=Path, default=REFERENCE_DIR)
    args = ap.parse_args(argv)
    if not args.label.replace("-", "").isalnum() or args.label != args.label.lower():
        print("S7_PROBE_BAD_LABEL", file=sys.stderr)
        return 2
    if not args.confirm_real:
        print(f"S7_PROBE_PLAN phép_thử=C0..C9 tiền_tố={PREFIX_ROOT}<mã lần chạy>/ luồng={THREADS} — KHÔNG gọi mạng. Thêm --confirm-real để chạy thật.")
        return 3
    settings, missing = read_settings()
    if settings is None:
        print(f"S7_PROBE_CONFIG_MISSING {','.join(missing)}", file=sys.stderr)
        return 2
    run_id = uuid.uuid4().hex[:12]
    started = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    suite = Suite(settings, run_id)
    print(f"S7_PROBE_START run={run_id} region={settings.region}")
    try:
        suite.run_all()
    finally:
        cleanup = suite.cleanup()
    for c in suite.checks:
        print(f"S7_PROBE_CHECK {c.id} {'OK' if c.ok else 'FAIL'}{'' if c.required else ' (thông tin)'} {c.ms}ms {json.dumps(c.facts, ensure_ascii=False, sort_keys=True)}")
    print(f"S7_PROBE_CLEANUP {json.dumps(cleanup)}")
    text = render_markdown(args.label, settings, run_id, started, suite.checks, cleanup)
    problems = self_check(text, settings.secrets())
    if problems:
        print(f"S7_PROBE_SELF_CHECK KHÔNG ĐẠT {problems}", file=sys.stderr)
        return 1
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / f"s7-{args.label}.md").write_text(text, encoding="utf-8")
    print(f"S7_PROBE_SELF_CHECK ĐẠT sha256={hashlib.sha256(text.encode()).hexdigest()}")
    if not args.no_publish:
        (args.reference_dir / f"object-storage-s7-{args.label}.md").write_text(text, encoding="utf-8")
        print(f"S7_PROBE_PUBLISHED docs/reference/object-storage-s7-{args.label}.md")
    failed = [c.id for c in suite.checks if c.required and not c.ok]
    if failed or cleanup.get("left") != 0:
        print(f"S7_PROBE_RESULT KHÔNG ĐẠT phép_thử_hỏng={failed} còn_lại={cleanup.get('left')}", file=sys.stderr)
        return 4 if not failed else 1
    print("S7_PROBE_RESULT ĐẠT")
    return 0


if __name__ == "__main__":
    sys.exit(main())
