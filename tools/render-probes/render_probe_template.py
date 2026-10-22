#!/usr/bin/env python3
"""Template GIẢ cho phép đo `soffice` trên Render (O1-6, bước 4 và 4b của runbook; ngoại lệ cổng 2.7, PO 2026-10-21): nạp trước khi đo, RETIRE ngay sau đo.

KHÔNG phải mã ứng dụng, không vào image. PO chạy trong image `bo19-runtime`, sau `render_probe_accounts.py seed` (cần tài khoản `DO-0001` làm người tải lên):

    docker run --rm --env-file <file-env> -v "${PWD}\\tools:/tools" bo19-runtime \\
        python /tools/render-probes/render_probe_template.py install --allow-host <host-ngoài-của-DB-Render>

`<file-env>` mang `BO19_MIGRATOR_DATABASE_URL` (role `bo19_migrator`, ghi `template` / `template_version` / `template_variable`) và nhóm `BO19_OBJECT_STORAGE_*`
(ENDPOINT_URL, BUCKET = `bo19-render-dev`, REGION = `auto`, ACCESS_KEY_ID, SECRET_ACCESS_KEY — token Object Read & Write của bucket RENDER, không phải `bo19-dev`). Không tham số nào mang credential.

Lệnh con:
  install   dựng `.docx` GIẢ (nhãn "(giả)", chỉ Times New Roman, không biến nội dung tự do → job render không gọi LLM), đưa lên R2 bằng đường `put_once` của ứng dụng,
            thêm `template` (`DO_RENDER_GIA`) + `template_version` ACTIVE + biến. Ghi **giờ nạp** vào `out/probe_window.json` và in (UTC và giờ Việt Nam) để PO ghi vào roadmap
  retire    chuyển `template_version` sang `RETIRED` (`retired_at`) — NGAY sau đo; ghi **giờ retire**. Đặt `RETIRED` khi còn `document` đang chờ render thì job đó trượt
            `TEMPLATE_NOT_ACTIVE_AT_RENDER`: chỉ retire khi không còn job `render_document` chạy

  check     (không chạm DB) chẩn đoán nhóm `BO19_OBJECT_STORAGE_*` khi `install` trượt `ACCESS_DENIED`: hình dạng các biến (endpoint, tên bucket, độ dài khoá — KHÔNG in giá trị) và bốn phép thử trên
            tiền tố `probe-check/` — `reachable`, liệt kê, ghi một object nhỏ, xoá nó — mỗi phép in `OK` hoặc mã lỗi. `ACCESS_DENIED` gộp ba nguyên nhân (khoá sai, bí mật/vùng sai, token thiếu quyền ghi hoặc
            không thuộc bucket này): các phép đọc đạt mà phép ghi trượt nghĩa là token không có quyền ghi vào bucket đó

Chặn: `--allow-host` đúng host DSN; role `bo19_migrator`; DB `NON_PRODUCTION`; cửa sổ ngoại lệ còn hiệu lực (`probe_window.json`, chưa thu hồi, chưa hết hạn); tài khoản `DO-0001` tồn tại;
**không có phiên bản `ACTIVE` nào khác** của loại `WORK_CONFIRMATION` (không đè lên template thật — `uq_template_version_one_active`) và chưa có template giả đang `ACTIVE`.
Object nằm ở bucket `bo19-render-dev` dưới `templates/<uuid>/source.docx`; template giả sau khi retire vẫn còn dòng trong DB (chỉ thêm — `template_version` đã `RETIRED`) và object trong bucket.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import os
import sys
import uuid
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import render_probe_accounts as acc  # noqa: E402

ENV_DSN = "BO19_MIGRATOR_DATABASE_URL"
CODE = "DO_RENDER_GIA"
NAME = "(giả) Mẫu đo Render — chỉ để thử"
UPLOADER = "DO-0001"
FONT = "Times New Roman"
# (tên biến, kiểu, slot nguồn, điền sau duyệt) — không có biến nội dung tự do: job `render_document` không gọi LLM
VARIABLES = (("full_name", "DIRECT_SLOT", "full_name", False), ("department_name", "DIRECT_SLOT", "department_name", False), ("job_title", "DIRECT_SLOT", "job_title", False),
             ("recipient_org", "DIRECT_SLOT", "recipient_org", False), ("document_number", "SYSTEM", None, True), ("issued_date", "SYSTEM", None, True), ("signer_user_id", "SYSTEM", None, True))


class TemplateRefused(Exception):
    """Mã từ chối, không chứa DSN hay giá trị."""


def template_docx() -> bytes:
    """`.docx` giả. Mẫu mặc định của python-docx mang sẵn bảng font, theme và kiểu có Calibri/Cambria/Arial/…: dọn để họ font khai CHỈ là Times New Roman (cùng cách với `_only_times_new_roman` của `tools/template-build/`; chép lại ở đây để công cụ này không phụ thuộc nhánh khác)."""
    from docx import Document
    doc = Document()
    for style in ("Normal", "Header", "Footer"):
        doc.styles[style].font.name = FONT
    for text in ("MẪU GIẢ (giả) — chỉ để đo trên Render, không phải mẫu của tổ chức", "{{ full_name }} — {{ department_name }} — {{ job_title }}", "Kính gửi: {{ recipient_org }}",
                 "Số: {{ document_number }} ngày {{ issued_date }} — người ký {{ signer_user_id }}"):
        doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return _only_times_new_roman(buf.getvalue())


_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _only_times_new_roman(blob: bytes) -> bytes:
    import zipfile

    from lxml import etree

    src, out = zipfile.ZipFile(io.BytesIO(blob)), io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename in ("word/styles.xml", "word/stylesWithEffects.xml", "word/numbering.xml"):
                root = etree.fromstring(data)
                for rf in root.iter(f"{{{_W}}}rFonts"):
                    for attr in list(rf.attrib):
                        del rf.attrib[attr]
                    for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
                        rf.set(f"{{{_W}}}{attr}", FONT)
                data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            elif item.filename == "word/fontTable.xml":
                data = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:fonts xmlns:w="{_W}"><w:font w:name="{FONT}"><w:family w:val="roman"/></w:font></w:fonts>').encode()
            elif item.filename.startswith("word/theme/") and item.filename.endswith(".xml"):
                root = etree.fromstring(data)
                for kind in ("majorFont", "minorFont"):
                    for node in root.iter(f"{{{_A}}}{kind}"):
                        for child in list(node):
                            if child.tag == f"{{{_A}}}font":
                                node.remove(child)
                        for tag, face in (("latin", FONT), ("ea", ""), ("cs", "")):
                            el = node.find(f"{{{_A}}}{tag}")
                            if el is not None:
                                el.set("typeface", face)
                data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            dst.writestr(item, data)
    return out.getvalue()


def storage_from_env(env=os.environ):
    from bo19.object_storage import ObjectStorage, ObjectStorageConfig
    names = ("BO19_OBJECT_STORAGE_ENDPOINT_URL", "BO19_OBJECT_STORAGE_BUCKET", "BO19_OBJECT_STORAGE_ACCESS_KEY_ID", "BO19_OBJECT_STORAGE_SECRET_ACCESS_KEY")
    if any(not env.get(n) for n in names):
        raise TemplateRefused("TEMPLATE_STORAGE_ENV_MISSING")
    return ObjectStorage(ObjectStorageConfig(endpoint_url=env[names[0]], bucket=env[names[1]], access_key_id=env[names[2]], secret_access_key=env[names[3]],
                                             region=env.get("BO19_OBJECT_STORAGE_REGION") or "auto"))


def check_storage(env=os.environ, *, storage=None, echo=print) -> int:
    """Chẩn đoán object storage, không lộ bí mật: hình dạng biến + bốn phép thử. Mã thoát 0 khi cả bốn đạt."""
    from bo19.object_storage import StorageError

    endpoint, bucket = env.get("BO19_OBJECT_STORAGE_ENDPOINT_URL", ""), env.get("BO19_OBJECT_STORAGE_BUCKET", "")
    shape = {"endpoint_https": endpoint.startswith("https://"), "endpoint_r2": endpoint.rstrip("/").endswith(".r2.cloudflarestorage.com"), "bucket_is_render_dev": bucket == "bo19-render-dev",
             "region": env.get("BO19_OBJECT_STORAGE_REGION") or None, "key_id_len": len(env.get("BO19_OBJECT_STORAGE_ACCESS_KEY_ID", "")), "secret_len": len(env.get("BO19_OBJECT_STORAGE_SECRET_ACCESS_KEY", "")),
             "edge_whitespace": any(env.get(k, "") != env.get(k, "").strip() for k in ("BO19_OBJECT_STORAGE_ENDPOINT_URL", "BO19_OBJECT_STORAGE_BUCKET", "BO19_OBJECT_STORAGE_ACCESS_KEY_ID",
                                                                                                "BO19_OBJECT_STORAGE_SECRET_ACCESS_KEY"))}
    echo("CHECK_SHAPE " + " ".join(f"{k}={v}" for k, v in shape.items()))
    storage = storage or storage_from_env(env)
    key = f"probe-check/{uuid.uuid4()}"

    def attempt(name: str, fn) -> bool:
        try:
            fn()
            echo(f"CHECK_{name} OK")
            return True
        except StorageError as e:
            echo(f"CHECK_{name} {e.code}")
        except Exception as e:  # noqa: BLE001 — chỉ tên lớp lỗi
            echo(f"CHECK_{name} {type(e).__name__}")
        return False

    ok = [attempt("REACHABLE", lambda: (_ for _ in ()).throw(StorageError("UNAVAILABLE")) if not storage.reachable() else None),
          attempt("LIST", lambda: list(storage.list_keys("probe-check/"))[:1]),
          attempt("PUT", lambda: storage.put_if_absent(key, b"probe", content_type="application/octet-stream")),
          attempt("DELETE", lambda: storage.delete(key))]
    echo("CHECK_RESULT " + ("OK" if all(ok) else "FAILED"))
    return 0 if all(ok) else 1


def _window(out: Path, at: dt.datetime) -> dict:
    w = acc.read_window(out)
    if not w or w.get("torn_down_at"):
        raise TemplateRefused("TEMPLATE_NO_ACTIVE_WINDOW")
    if dt.datetime.fromisoformat(w["expires_at"]) < at:
        raise TemplateRefused("TEMPLATE_WINDOW_EXPIRED")
    return w


def _stamp(t: dt.datetime) -> str:
    vn = t.astimezone(dt.timezone(dt.timedelta(hours=7)))
    return f"{t.isoformat(timespec='seconds')} (giờ Việt Nam {vn.strftime('%Y-%m-%d %H:%M:%S')})"


def install(dsn: str, storage, *, allow_host: str, out: Path = acc.OUT, now: dt.datetime | None = None, lease_s: float = 120, echo=print) -> dict:
    from bo19.persistence.pool import Pool
    from bo19.tool_layer import storage as store

    now = now or dt.datetime.now(dt.timezone.utc)
    window = _window(out, now)
    with acc._connect(dsn, allow_host=allow_host) as conn:
        uploader = conn.execute("select id from employee where id = %s and is_active", (acc.employee_id(UPLOADER),)).fetchone()
        if uploader is None:
            raise TemplateRefused("TEMPLATE_NO_UPLOADER_ACCOUNT")
        active = conn.execute("select t.code from template t join template_version v on v.template_id = t.id where t.request_type_code = 'WORK_CONFIRMATION' and v.status = 'ACTIVE'").fetchall()
        if active:
            raise TemplateRefused("TEMPLATE_ACTIVE_ALREADY_EXISTS")  # kể cả template giả cũ: retire trước; không bao giờ đè lên template thật
        key = f"templates/{uuid.uuid4()}/source.docx"
        pool = Pool(dsn, application_name="bo19-render-probe-template", min_size=1, max_size=2)
        pool.open()
        try:
            store.put_once(pool, storage, object_key=key, purpose="TEMPLATE_SOURCE", content_type="application/octet-stream", data=template_docx(), lease_s=lease_s)
        finally:
            pool.close()
        tid, vid = uuid.uuid4(), uuid.uuid4()
        n = conn.execute("select coalesce(max(version_no), 0) + 1 from template_version v join template t on t.id = v.template_id where t.code = %s", (CODE,)).fetchone()[0]
        row = conn.execute("select id from template where code = %s", (CODE,)).fetchone()
        if row is None:
            conn.execute("insert into template (id, code, request_type_code, name) values (%s, %s, 'WORK_CONFIRMATION', %s)", (tid, CODE, NAME))
        else:
            tid = row[0]
        conn.execute("insert into template_version (id, template_id, version_no, status, source_object_key, uploaded_by_employee_id, required_fonts, activated_at) values (%s, %s, %s, 'ACTIVE', %s, %s, %s, now())",
                     (vid, tid, n, key, uploader[0], [FONT]))
        for name, kind, source, after in VARIABLES:
            conn.execute("insert into template_variable (template_version_id, variable_name, kind, source_slot_name, fill_after_approval) values (%s, %s, %s, %s, %s)", (vid, name, kind, source, after))
        conn.commit()
    window.update({"template_installed_at": now.isoformat(timespec="seconds"), "template_version_id": str(vid), "template_retired_at": None})
    acc.write_window(out, window)
    echo(f"PROBE_TEMPLATE_INSTALLED code={CODE} version_no={n} installed_at={_stamp(now)}")  # PO ghi giờ này vào roadmap
    return window


def retire(dsn: str, *, allow_host: str, out: Path = acc.OUT, now: dt.datetime | None = None, echo=print) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    window = acc.read_window(out)
    if not window or not window.get("template_version_id"):
        raise TemplateRefused("TEMPLATE_NOTHING_TO_RETIRE")
    with acc._connect(dsn, allow_host=allow_host) as conn:
        done = conn.execute("update template_version set status = 'RETIRED', retired_at = %s where id = %s and status = 'ACTIVE'", (now, window["template_version_id"])).rowcount
        conn.commit()
    window["template_retired_at"] = now.isoformat(timespec="seconds")
    acc.write_window(out, window)
    echo(f"PROBE_TEMPLATE_RETIRED rows={done} retired_at={_stamp(now)}")
    return window


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("install", "retire"):
        sub.add_parser(name).add_argument("--allow-host", required=True, help="host của DSN Render (khai tường minh)")
    sub.add_parser("check")
    a = ap.parse_args()
    if a.cmd == "check":  # không cần DSN
        try:
            return check_storage()
        except TemplateRefused as e:
            print(f"PROBE_REFUSED {e}", file=sys.stderr)
            return 1
    dsn = os.environ.get(ENV_DSN, "")
    if not dsn:
        print(f"THIẾU {ENV_DSN}", file=sys.stderr)
        return 2
    try:
        if a.cmd == "install":
            install(dsn, storage_from_env(), allow_host=a.allow_host)
        else:
            retire(dsn, allow_host=a.allow_host)
    except (TemplateRefused, acc.ProbeRefused) as e:
        print(f"PROBE_REFUSED {e}", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001
        from bo19.object_storage import StorageError

        if isinstance(e, StorageError):  # thay cho traceback: chỉ mã; chạy `check` để chẩn đoán
            print(f"PROBE_REFUSED TEMPLATE_STORAGE_{e.code} (chạy `check` để chẩn đoán, không lộ bí mật)", file=sys.stderr)
            return 1
        raise
    except psycopg.Error as e:
        print(f"PROBE_DB_ERROR {type(e).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
