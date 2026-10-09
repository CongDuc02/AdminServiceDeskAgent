-- =============================================================================
-- BO-19 Admin Service Desk Agent — schema migration 0010
-- ADR-019, mục Bổ sung B5 (PO, 2026-10-09): dòng llm_usage ước lượng khi provider không
-- trả usage cho một lần thử có thể đã sinh token; thời lượng mỗi lời gọi.
-- Diễn giải: docs/design/04-data.md, đoạn "Ba cột thêm ở B5" ở phần llm_usage;
-- docs/design/11-ops.md mục 10.5; A-092.
-- =============================================================================
--
-- Áp SAU 0009_llm_usage_reasoning_tokens.sql, bằng bo19_migrator, trong một giao
-- dịch riêng (ADR-017). KHÔNG sửa 0001_initial.sql / contracts/schema.sql hay
-- migration nào trước.
--
-- Chỉ thêm số và cờ — luật "không văn bản" của llm_usage không đổi.
-- Không GRANT mới: bo19_app đã có SELECT, INSERT trên cả bảng llm_usage (nhóm
-- "Chỉ thêm" của 04-data.md); cột mới nằm trong quyền đó.
-- =============================================================================

-- true: dòng có phần token ƯỚC LƯỢNG (input = byte UTF-8 của thân request, output =
-- max_completion_tokens của module) cho các lần thử không có usage.
ALTER TABLE llm_usage ADD COLUMN estimated boolean NOT NULL DEFAULT false;

-- Thời lượng phía client của cả lời gọi `call` (mọi lần thử, quãng nghỉ, lần sửa parse).
-- NULL ở ca từ chối trước khi tới provider.
ALTER TABLE llm_usage ADD COLUMN duration_ms integer;

-- Tổng usage.completion_time provider báo (mili giây). NULL khi bất kỳ phản hồi nào
-- thiếu nó hoặc có lần thử không có usage — không suy ra.
ALTER TABLE llm_usage ADD COLUMN provider_completion_ms integer;

ALTER TABLE llm_usage ADD CONSTRAINT ck_llm_usage_durations
    CHECK ((duration_ms IS NULL OR duration_ms >= 0) AND (provider_completion_ms IS NULL OR provider_completion_ms >= 0));

-- Dòng ước lượng có output ước lượng, và chỉ ở bốn kết quả có lời gọi tới provider:
-- hai ca từ chối và BUDGET_UNAVAILABLE không bao giờ ước lượng (fail-closed ở tầng ứng dụng,
-- không ở đây: ADR-019 ca 1 đến 3).
ALTER TABLE llm_usage ADD CONSTRAINT ck_llm_usage_estimated_shape
    CHECK (NOT estimated OR (output_tokens IS NOT NULL AND outcome IN ('OK', 'PARSE_REPAIRED', 'PARSE_FAILED', 'PROVIDER_ERROR')));
