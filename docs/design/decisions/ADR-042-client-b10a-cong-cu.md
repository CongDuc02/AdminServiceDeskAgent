# ADR-042 — Client B10a: React Router, Vitest + Testing Library + MSW, npm, CSS thường, Node LTS ghim theo digest

**Trạng thái:** Accepted · **Duyệt:** PO, 2026-10-21 (sáu câu của `proposals/b10a-ke-hoach.md`, theo mặc định) · **Ngày:** 2026-10-21 · **Quyết định tại:** BUILD MODE, trước mã B10a · **Liên quan:** ADR-018 (Vite, TanStack Query, ESLint, `openapi-typescript`), ADR-013, mục 10 của `06-structure.md`

---

## Context

ADR-018 chốt Vite, TanStack Query, ESLint và type sinh từ `openapi.yaml` nhưng để ngỏ bốn thứ client cần ngay ở B10a: thư viện định tuyến, bộ kiểm thử, công cụ quản lý gói, cách tạo kiểu giao diện. Luật của dự án: mọi công nghệ ngoài danh sách bắt buộc cần ADR có ít nhất một phương án bị loại.

## Options

- **Định tuyến:** (A) React Router; (B) TanStack Router; (C) tự viết trên `history`.
- **Kiểm thử:** (A) Vitest + Testing Library + MSW; (B) Jest + Testing Library; (C) Cypress/Playwright làm bộ chính.
- **Quản lý gói:** (A) npm; (B) pnpm; (C) yarn.
- **Kiểu giao diện:** (A) CSS thường (CSS modules), không thư viện UI; (B) một thư viện UI (MUI, Ant, …); (C) Tailwind.
- **Node:** (A) bản LTS đang hỗ trợ tại ngày dựng, ghim ảnh theo digest; (B) bản mới nhất.

## Decision

**React Router · Vitest + Testing Library + MSW · npm · CSS modules · Node LTS ghim theo digest.** Số phiên bản chính xác ghi vào `package.json`/`package-lock.json` và mục Triển khai ở B10a của `06-structure.md`; số hiệu và hành vi lấy từ tài liệu gốc đặt vào `docs/reference/` **trước khi dựa vào** (luật PO 2026-10-04), không từ trí nhớ.

- Router khai tuyến theo mục 10.3; đường dẫn SPA không bắt đầu bằng `/api` (ADR-018). Mọi tuyến sau `AuthGate`, trừ `/login`.
- Vitest dùng chung cấu hình Vite (không cấu hình ESM thứ hai); MSW chặn tầng mạng nên **lối `fetch` duy nhất vẫn là đối tượng được kiểm** (không mock hàm của `http.ts`).
- Test ESLint (chứng minh luật cấm bằng vi phạm cố ý) chạy bằng API của ESLint trong Vitest.
- npm đi kèm ảnh Node: không thêm công cụ ngoài image build client.
- CSS modules: không phụ thuộc thư viện UI; nhãn trạng thái luôn do server trả (ADR-018).
- Node: LTS đang hỗ trợ tại ngày dựng; ghim theo digest như ảnh Python (cùng nguyên tắc ADR-030).

## Consequences

**Tích cực:** một chuỗi công cụ (Vite) cho dev, build và test; không phụ thuộc thư viện UI; kiểm được luật ranh giới bằng chính ESLint; lockfile duy nhất.

**Tiêu cực / phải chấp nhận:** tự viết CSS cho từng trang (chấp nhận ở quy mô B10a/B10b); trình duyệt thật chưa nằm trong bộ test tự động của B10a — một lần chạy tay ghi vào báo cáo, xét lại ở B10b/AC-1.1.

## Rejected alternatives

- **TanStack Router** — thêm một hệ type-route song song với type sinh từ `openapi.yaml`, không cần ở quy mô 4 tuyến.
- **Tự viết định tuyến trên `history`** — viết lại phần có thư viện chuẩn (điều hướng, tham số, chặn tuyến) chỉ để bớt một phụ thuộc.
- **Jest** — cần cấu hình biến đổi ESM/TypeScript riêng cho một dự án đã dùng Vite; chạy chậm hơn trên cùng bộ test.
- **Cypress/Playwright làm bộ chính** — nặng (trình duyệt trong CI), chậm; có giá trị cho hành trình AC-1.1 nên xét ở B10b, không thay test đơn vị/thành phần.
- **pnpm, yarn** — thêm công cụ ngoài image Node mà không có lợi ích ở một gói client.
- **Thư viện UI / Tailwind** — kéo theo hệ thiết kế và phụ thuộc lớn cho vài màn hình; chưa có yêu cầu nhận diện thương hiệu (PO 2026-10-21: không).
- **Node bản mới nhất** — không phải bản hỗ trợ dài hạn; rủi ro đổi giữa chừng.
