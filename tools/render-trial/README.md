# `tools/render-trial/` — chạy job `render_document` với Groq thật (B9a)

Không phải mã ứng dụng, không vào image. PO duyệt 2026-10-13 (kế hoạch B9a, Q5): **tối đa 10 lời gọi Groq**, văn bản "(giả)", cờ `--confirm-real`.

## Làm gì

Chạy **đường thật** của B9a trên một PostgreSQL local dùng tạm và một bucket SeaweedFS tạm: `request_submit` → job `render_document` → `Dispatcher` → `DocumentRunner.run_render` (graph, checkpointer, tool, `soffice`,
object storage) → `PENDING_APPROVAL`. Chỉ P4 `draft_free_content` đi tới Groq. Mỗi job in/ghi: trạng thái job và `document`, thời lượng cả job, từng lời gọi (ms, ms phía provider, token), kết quả `validate_free_content`
(số lần sinh, `PASSED`/`FAILED`, **độ dài** — không văn bản), và kiểm bằng máy của M5 trên PDF vừa dựng: `pdfinfo` đọc `Subject` (đúng chuỗi watermark), `Author` (tên hệ thống), và cột `document_render.watermark_text`.

## Luật (PO)

- **Chỉ văn bản bịa có nhãn "(giả)"** (A-080): `purpose` và `recipient_org` của mọi job đều mang nhãn. Tool **không** ghi văn bản do LLM sinh, không ghi giá trị slot — chỉ số, mã, cờ.
- **Tối đa 10 lời gọi Groq** (`MAX_CALLS`): mỗi job chừa 4 lời gọi (một lần sinh, một lần sinh lại, hai lần sửa parse); không đủ chỗ thì dừng. `--runs` từ 1 tới 6 (mặc định 3). Giãn nhịp dưới 6.500 token/phút.
- **Khoá API chỉ từ biến môi trường `BO19_LLM_API_KEY`**; không trên dòng lệnh, không in, không ghi; tool không đọc `.env`.
- **Gọi mạng thật chỉ khi có `--confirm-real`** — không có cờ này tool chỉ in kế hoạch và thoát mã `3`.

## Chạy

Cần `pg` và `bo19-s3` đang chạy trên network `ci` (`docker start pg bo19-s3`; credential S3 test ở file env tạo bởi `tools/object-storage-local/start.sh`) và image `bo19-test` (`docker build --target test -t bo19-test .` — có `soffice`, `pdfinfo`).

```bash
read -rs BO19_LLM_API_KEY; echo; export BO19_LLM_API_KEY
MSYS_NO_PATHCONV=1 docker run --rm --network ci --env-file <file-env-s3-ngoài-repo> -v "$PWD":/repo -w /repo \
  -e BO19_LLM_API_KEY -e BO19_TRIAL_PG_ADMIN_DSN=postgresql://postgres@pg:5432/postgres -e PYTHONPATH=/repo/backend/src \
  --entrypoint python bo19-test tools/render-trial/render_trial.py --confirm-real
unset BO19_LLM_API_KEY
```

Tuỳ chọn: `--runs N` · `--label b9a` (kết quả ghi `docs/reference/render-trial-<nhãn>.md`) · `--no-publish`.
Mã thoát: `0` xong · `2` thiếu biến môi trường (chỉ nêu tên) hay tham số sai · `3` chưa `--confirm-real`.

`backend/tests/test_render_trial.py` chạy toàn bộ tool với provider giả ở mỗi lần CI (không mạng, không khoá thật), kể cả phép thử "không vượt 10 lời gọi khi mọi lời gọi hỏng".
