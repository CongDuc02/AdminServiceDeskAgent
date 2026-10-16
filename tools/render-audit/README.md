# `tools/render-audit/` — kiểm watermark của bản render sau UAT (M5, B9a)

Không phải mã ứng dụng, không vào image `runtime`. Thủ tục đầy đủ: mục 18 của `docs/design/11-ops.md`. Quyết định: `docs/design/decisions/ADR-038-watermark-trong-metadata-pdf.md`.

Với mỗi dòng `document_render`, kiểm **ba chân độc lập** — DB (`watermark_text`), checksum (byte PDF so với `stored_object_commit`), metadata (`pdfinfo` đọc `Subject`) — và một chân phụ (`Author` của PDF là tên hệ thống). Chạy **trong image `test`** vì cần `pdfinfo` (poppler); runtime không đọc lại PDF.

```bash
docker build --target test -t bo19-test .
docker run --rm --env-file <file-env-ngoài-repo> -v "$PWD":/repo -w /repo/backend -e PYTHONPATH=src \
  --entrypoint python bo19-test /repo/tools/render-audit/render_audit.py [--document-id <uuid>] [--limit N]
```

Credential chỉ qua `--env-file` (file ngoài repo): `BO19_DATABASE_URL` (role `bo19_app`, chỉ `SELECT`), `BO19_OBJECT_STORAGE_ENDPOINT_URL`, `BO19_OBJECT_STORAGE_BUCKET`, `BO19_OBJECT_STORAGE_ACCESS_KEY_ID`, `BO19_OBJECT_STORAGE_SECRET_ACCESS_KEY`. Không có tham số dòng lệnh nào nhận credential; script không in credential, không in nội dung văn bản hay giá trị slot.

Mã thoát: `0` mọi dòng đạt · `1` có dòng trượt (in `render_id`, `document_id`, loại bản, chế độ, mã trượt) · `2` không kiểm được (thiếu `pdfinfo`, thiếu biến, lỗi DB) — không bao giờ in "đạt". Số dòng đã kiểm luôn được in.

Test: `backend/tests/test_render_audit.py`.
