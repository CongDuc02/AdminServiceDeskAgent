"""Tiến trình thăm dò bộ nhớ của `storage.fetch_verified` (B8c) — chạy RIÊNG, do `test_files_stream` gọi; không phải test.

Đọc `PROBE_DSN` (DSN `bo19_app` của DB thử) và `PROBE_BUCKET`, cộng `BO19_TEST_S3_*`; tải object `argv[1]` bằng `fetch_verified`, đọc hết tệp tạm theo khối 256 KiB (như response làm), rồi in MỘT dòng JSON
`{"size", "delta_mib"}` — `delta_mib` là mức tăng của RSS ĐỈNH (`VmHWM`) so với ngay trước khi tải. Một tiến trình riêng cho mỗi phép đo để RSS đỉnh của lần này không dính lần khác.
"""
from __future__ import annotations

import json
import os
import sys

from bo19.persistence.pool import Pool
from bo19.tool_layer import storage as st
from tests.s3_support import storage_for


def hwm_kib() -> int:
    with open("/proc/self/status") as f:
        return next(int(line.split()[1]) for line in f if line.startswith("VmHWM:"))


def main() -> None:
    key = sys.argv[1]
    pool = Pool(os.environ["PROBE_DSN"], application_name="bo19-rss-probe", min_size=1, max_size=1)
    pool.open()
    storage = storage_for(os.environ["PROBE_BUCKET"])
    # khởi động boto và kết nối trước khi đo: chi phí cố định không được tính vào "mức tăng theo kích thước file"
    storage.head(key)  # một lệnh nhỏ: nạp mô-đun, nối TLS, ký — mọi chi phí cố định của lần đầu
    warm = st.committed(pool, key)
    before = hwm_kib()
    if len(sys.argv) > 2 and sys.argv[2] == "buffered":  # đối chứng: đường cũ của B8b — cả object trong bộ nhớ
        data = st.fetch(pool, storage, key, max_bytes=256 * 1024 * 1024)
        size = total = len(data)
    else:
        f, size = st.fetch_verified(pool, storage, key, max_bytes=256 * 1024 * 1024)
        with f:
            total = 0
            while chunk := f.read(256 * 1024):
                total += len(chunk)
    pool.close()
    assert total == size == warm.size_bytes
    print(json.dumps({"size": size, "delta_mib": round((hwm_kib() - before) / 1024, 2)}))


if __name__ == "__main__":
    main()
