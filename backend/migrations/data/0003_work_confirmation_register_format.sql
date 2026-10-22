-- =============================================================================
-- BO-19 Admin Service Desk Agent — data migration 0003
-- M1.2 (PO chốt 2026-10-21): khuôn số của giấy xác nhận công tác, hai dải.
-- Nguồn: docs/design/04-data.md mục 4.1 (Khuôn của PO); docs/design/decisions/ADR-043-so-van-ban-duy-nhat-theo-ky.md;
--        docs/reference/nghi-dinh-30-2020-so-ky-hieu-van-ban.md (đánh lại từ 01 mỗi năm; số < 10 thêm số 0).
-- =============================================================================
--
-- Áp SAU mọi schema migration (kể cả 0015), bằng bo19_migrator, trong một giao dịch riêng (ADR-017, bước 4). Chỉ INSERT.
--
-- Chữ in trên văn bản là `Số: {seq}/GXN-{VIẾT_TẮT}`; nhãn `Số:` nằm trong MẪU .docx, `format_pattern` chỉ giữ phần số.
--   OFFICIAL  `{seq}/GXN-{symbol}`      → 01/GXN-ABC
--   TRIAL     `{seq}/GXN-{symbol}-TN`   → 01/GXN-ABC-TN   (PO: số thử nghiệm không bao giờ trùng dạng số thật; vẫn là chữ in hoa nối bằng `-`)
-- `symbol = ABC` do PO cung cấp (2026-10-21). `GXN` là ký hiệu loại do công ty tự đặt (không có trong Phụ lục III của Nghị định 30/2020).
-- `seq_min_digits = 2`: số nhỏ hơn 10 thêm số 0 phía trước (Phụ lục I, Phần I mục II.3.c).
--
-- Khuôn không có `{year}`; số lặp lại mỗi năm vì `uq_register_entry_number` là duy nhất theo KỲ (migration 0015, ADR-043).
--
-- `effective_from` = 2026-10-21 00:00 giờ Việt Nam: bản ghi chỉ thêm, đổi khuôn là thêm dòng mới với `effective_from` mới.
-- id cố định (uuid5 theo sổ) để mọi môi trường có cùng id. Không dòng nào trong file này là dữ liệu giả; dữ liệu giả của test và của seed local
-- tự dựng khuôn riêng (xoá các dòng này trong fixture của chúng).
--
-- TƯƠNG THÍCH NGƯỢC: chỉ thêm hai dòng; mã đang live chọn dòng có `effective_from` lớn nhất không sau thời điểm cấp, nên sau khi áp, lần phát hành kế tiếp
-- của dải đó dùng khuôn mới (trước đó dải `TRIAL` trên Render không có khuôn nào — `NO_FORMAT`).
-- =============================================================================

INSERT INTO document_register_format (id, document_register_id, series, format_pattern, symbol, seq_min_digits, effective_from) VALUES
    ('7d76170a-beca-5e67-8d87-6986088c565d', '7c2f0e1a-5b3d-4c8e-9a41-1d6b7e90a001', 'TRIAL',    '{seq}/GXN-{symbol}-TN', 'ABC', 2, timestamptz '2026-10-21 00:00:00+07'),
    ('00a212dd-9660-5c5d-b80d-9945eaa34e30', '7c2f0e1a-5b3d-4c8e-9a41-1d6b7e90a001', 'OFFICIAL', '{seq}/GXN-{symbol}',    'ABC', 2, timestamptz '2026-10-21 00:00:00+07');
