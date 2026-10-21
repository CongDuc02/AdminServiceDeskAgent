# Kế hoạch B10a — client nửa nhân viên: khung SPA, `/login`, `/chat`, `/my-requests`, ESLint của AC-1.12, bước kiểm #8, luật 404 phía client

**Trạng thái:** đề xuất, **chờ PO duyệt** — chưa viết dòng mã nào · **Ngày:** 2026-10-21 · **Căn cứ:** `12-roadmap.md` (Sprint 1, dòng B10a·B10b; AC-1.12; AC-1.1 nửa nhân viên; O1-8), mục Cây frontend, Luật import, Đặc tả luật ESLint, Tuyến, Phục vụ tĩnh và luật 404, Auth flow của `06-structure.md`; ADR-013, ADR-018; mục Chat, Yêu cầu, Tải file của `05-api.md` · **Migration:** không · **Biến môi trường mới:** không · **Đổi `openapi.yaml`:** không (client dùng contract như đã có; nếu lúc làm thấy cần thêm trường, dừng và báo diff trước — luật PO 2026-10-21) · **Chặn bởi:** không. Backend của nửa nhân viên đã có từ B3, B6b, B8b, B9b2: `POST/DELETE /auth/session`, `GET /me`, `POST /chat-sessions`, `GET …/messages`, `POST …/turns` (SSE), `GET /requests`, `GET /requests/{id}` (nay có `documents`), `confirm-slots`, `submit`, `downloadRender`.

## Mục tiêu

Một nhân viên mở trình duyệt, đăng nhập, nói chuyện với agent, thấy yêu cầu của mình được mở và điền, xác nhận hồ sơ từng slot, gửi, theo dõi trạng thái tới `ISSUED` và tải bản `FINAL` của chính mình. Nửa cán bộ (`/review`, `/issue`, `/documents/:id`) là B10b. Sau B10b mới chạy AC-1.1.

## Phạm vi

| Hạng mục | Làm gì | Căn cứ |
|---|---|---|
| **Khung** | Vite + React + TypeScript; TanStack Query; router; `npm`; Node LTS ghim theo digest; `main.tsx`, `app/` (router, `QueryClient`, `AuthGate`, khung trang, **dải báo chế độ thử nghiệm** khi `Me.operating_mode = NON_PRODUCTION`) | ADR-018; mục 10, 11 của `06-structure.md` |
| **Lối `fetch` duy nhất** | `api/transport/http.ts`: `X-BO19-CSRF` cho mọi lệnh không phải GET, `credentials: 'same-origin'`, phân tích `ErrorEnvelope`, đọc body dạng stream; `api/transport/sse.ts`; `api/errors.ts` rẽ nhánh theo `error_code`, hiện `message` của server nguyên văn (NFR-04); 401 ở đâu cũng xoá cache và về `/login` | ADR-018 |
| **Type sinh từ contract** | `openapi-typescript` → `api/generated/openapi.d.ts`, commit; CI sinh lại và đỏ nếu lệch | ADR-018 |
| **`/login`** | Mã nhân viên + mật khẩu; một thông báo của server cho sai thông tin (không nói sai ở đâu); `GET /me` sau đăng nhập; đăng xuất | mục 11 |
| **`/chat`** | `POST /chat-sessions`, danh sách tin nhắn (`GET …/messages`), ô soạn (đếm tới WV-15 = 2.000 ký tự), `turnStream.ts` (ngoài TanStack Query): `Idempotency-Key` mỗi lượt, `turn.accepted/progress/reply/error`, **luật dựng lại khi stream đứt** (GET messages → gửi lại cùng khoá → `TURN_NOT_FINISHED` + `Retry-After` / `turn_abandoned`), hiện `pending_question` và `active_request`; kết thúc lượt thì invalidate `['my-requests']` | ADR-018; mục SSE của `05-api.md` |
| **`/my-requests` · `/my-requests/:requestId`** | Danh sách `scope=OWN`; chi tiết: bảng slot (độ nhạy, provenance của `HR_PROFILE`, giá trị đã xoá hiện "nội dung đã xoá"), **xác nhận từng slot** (`expected_row_version` của slot), thanh **gửi** (`submit_ready`, `failed_rules`, `missing_slots`), `status_label` của server (client không giữ bảng tên trạng thái), mục `documents` (`DocumentOwnerView`): số văn bản, ngày, nút **tải bản `FINAL` pdf** chỉ khi `ISSUED` | mục Yêu cầu của `05-api.md` |
| **ESLint (AC-1.12)** | Cấu hình flat config theo mục 10.2: cấm `fetch`/`EventSource` ngoài hai module, cấm `components` import `features|api|signals|auth`, cấm `features/*` import `api/transport`, cấm `features/<x>` import `features/<y>`; **test chứng minh bằng một vi phạm cố ý cho từng luật** (ESLint API trong Vitest, như `test_import_contracts.py`); job `frontend` trong `ci.yml` | AC-1.12 |
| **Phục vụ tĩnh + luật 404 (O1-8, phần client)** | `api` phục vụ `/app/static`: asset thật; file lạ dưới thư mục asset → 404 (không `index.html`); GET lạ còn lại → `index.html`; `/api/*` vẫn `ErrorEnvelope` (đã có). Dockerfile giai đoạn build client (đã đặc tả, `COPY --from=client-build`) | mục 10.4 |
| **Bước kiểm khởi động #8** | `index.html` và danh sách asset có mặt trong bản build; **Chặn** | `06-structure.md` mục bước kiểm |

**Không làm ở B10a:** `/review`, `/issue`, `/documents/:id` (B10b); `GET /signals`/`EventSource`/`notifications` (Sprint 3 — mục Endpoint → sprint); `request_cancel` (Sprint 2: không có nút huỷ); `/requests`, `/config/*`, `/audit` (Sprint 3+); i18n; mobile.

## Cách làm

Một nhánh `build/b10a-client`, ba mốc commit để PO xem được từng phần: **(1)** khung + transport + type sinh + ESLint + job CI + phục vụ tĩnh + bước kiểm #8 + `/login`; **(2)** `/chat`; **(3)** `/my-requests` + tải file. Docs-first như mọi lát: `06-structure.md` mục Triển khai ở B10a, `CHANGELOG.md`, ADR-042 (dưới), cập nhật `12-roadmap.md`.

**Tài liệu sản phẩm lấy bằng `curl` vào `docs/reference/` trước khi dựa vào** (luật PO 2026-10-04): ESLint (flat config, `no-restricted-globals/properties/imports`), Vite (build, `base`, proxy dev), TanStack Query (phiên bản chọn), router, `openapi-typescript`, Vitest/Testing Library. Cú pháp flat config đang `[CẦN XÁC MINH]` ở mục 10.2 — đóng bằng tài liệu này. Digest ảnh Node: lấy khi dựng và ghi vào `docs/reference/`.

**Kiểm:** Vitest (đơn vị: transport — CSRF, `ErrorEnvelope`, stream; `sse.ts`; `turnStream` với `fetch` giả cho từng nhánh dựng lại; ánh xạ `error_code`; ẩn hiện theo permission), Testing Library (từng trang với server giả), test ESLint (vi phạm cố ý), `tsc --noEmit`, `vite build`, kiểm lệch type sinh; phía backend: test phục vụ tĩnh (thư mục build giả) và bước kiểm #8. Một lần chạy tay trên local với trình duyệt thật ghi vào báo cáo (chưa tự động hoá trình duyệt ở B10a). Đột biến: ≥ một mẫu cho mỗi luật ESLint, mỗi nhánh dựng lại, luật 404, #8.

## Điều anh cần quyết (mặc định in đậm)

1. **Làm mới dữ liệu khi chưa có `GET /signals` (Sprint 3).** ADR-018 chỉ định tín hiệu SSE làm mới cache; B10a chưa có tín hiệu nên nhân viên không thấy `ISSUED` trừ khi tải lại. Mặc định: **lấy lại khi mở màn hình và khi cửa sổ lấy lại tiêu điểm (đúng ADR-018 cho query ngoài chủ đề), cộng `refetchInterval` 10 s CHỈ ở trang chi tiết yêu cầu khi `documents` còn trạng thái chưa cuối; gỡ khi Sprint 3 có tín hiệu.** Đây là thêm so với ADR-018 nên cần anh duyệt; phương án khác: không polling, chỉ nút "Làm mới".
2. **Chồng kiểm thử và router** — công nghệ ngoài danh sách bắt buộc nên cần ADR-042 (có phương án bị loại): mặc định **React Router (router), Vitest + Testing Library + MSW (kiểm), npm (quản lý gói)**; loại: Jest (nặng hơn, cấu hình ESM/Vite riêng), Cypress/Playwright (trình duyệt thật — để B10b/AC-1.1 xét), pnpm/yarn (thêm công cụ ngoài image Node). Anh có ưu tiên khác không?
3. **Tải bản `FINAL`:** mặc định **qua lối `fetch` duy nhất rồi lưu blob**, để lỗi (`FILE_UNAVAILABLE`…) hiện thông báo của server thay vì trang JSON thô. Phương án khác: liên kết `<a href>` trực tiếp (đơn giản hơn, mất thông báo lỗi).
4. **Giao diện:** mặc định **CSS thường (CSS modules), không thư viện UI**, tiếng Việt, một cột, đọc được ở rộng 360 px; nhãn trạng thái luôn do server trả. Cần thư viện UI/nhận diện thương hiệu nào không?
5. **Chia mốc:** mặc định **một nhánh, ba mốc commit** (mục Cách làm) và báo cáo một lần cuối; hay anh muốn xin merge sau mốc (1) để CI `frontend` lên `main` sớm?
6. **Node:** mặc định **bản LTS đang hỗ trợ tại ngày dựng, ghim theo digest** (số hiệu lấy từ tài liệu gốc lúc làm, không từ trí nhớ).

## Rủi ro

- **R-B10a-1 — Chat là phần khó:** stream lượt, dựng lại khi đứt, `TURN_NOT_FINISHED`; giảm bằng test `turnStream` theo từng nhánh trước khi dựng giao diện.
- **R-B10a-2 — Phục vụ tĩnh nuốt 404 của API** (O1-8): test hai chiều (`/api/lạ` → envelope; `/assets/lạ.js` → 404; `/my-requests/x` → `index.html`).
- **R-B10a-3 — Render PER/RES:** bảng slot hiển thị `PER`/`RES` cho chính chủ; không ghi giá trị vào `localStorage`/log console; test kiểm không có `console.*` mang giá trị.
- **R-B10a-4 — CI chậm/đỏ do Node:** job `frontend` tách khỏi job `backend`; cache theo lockfile.

## Open Questions

Sáu câu ở trên. Không có mục mở khác của roadmap bị chặn bởi B10a.
