# Công cụ client B10a — cú pháp và phiên bản lấy từ tài liệu gốc (ADR-018, ADR-042)

- **Lấy bằng `curl` ngày 2026-10-21**, không qua công cụ tóm tắt web. Bản HTML không vào repo (lớn, dựng bằng JavaScript); đây là các dòng **nguyên văn** từ bản chữ của từng trang cùng sha256 của bản HTML đã tải. Tài liệu sống — có thể đổi sau ngày lấy.
- **Dùng cho:** `frontend/` (B10a), `eslint.config.js` (AC-1.12), `vite.config.ts`, các test. **Phiên bản cài** ghi ở mục 2 (lấy từ `package-lock.json`, không từ trí nhớ).
- Những điều **chỉ biết được bằng chạy thật** ghi ở mục 3 (chưa có trong tài liệu đã tải).

## 1. Trang đã tải

| Tên | URL | sha256 của bản tải |
|---|---|---|
| node-release-schedule | `https://raw.githubusercontent.com/nodejs/Release/main/schedule.json` | `1cf0432ceb9dfde7f1fd4cce43206519942cfdfad5a26039c2f4bb20fde8549c` |
| eslint-config | `https://eslint.org/docs/latest/use/configure/configuration-files` | `5936a41a5cd6376444d3198247c2ad30af1461a2b8ad1a05424006c87f80cc77` |
| eslint-restricted-globals | `https://eslint.org/docs/latest/rules/no-restricted-globals` | `a5b4cc1a612aa68550545761f2cd05b095a3e5986e0ded8adec0095de126fd54` |
| eslint-restricted-imports | `https://eslint.org/docs/latest/rules/no-restricted-imports` | `065046441f42fdadc25448dff94d6f48525feb1d2dde2536ee643ac3ca282a47` |
| eslint-restricted-properties | `https://eslint.org/docs/latest/rules/no-restricted-properties` | `df8ab973a456c607a5612c8003c674c13eb1328763c19624dc674179a0cedb0a` |
| vite-server | `https://vite.dev/config/server-options` | `269b5a5e2ff250780e84140e5592a6e46a543cb38d052a5f4e60a7653b7c494b` |
| vite-build | `https://vite.dev/config/build-options` | `510d64c9238d703007297063a573d50c4cff849c56fd5c7458da5057b02b05fa` |
| vite-shared | `https://vite.dev/config/shared-options` | `4a60d3f7b257617186a04fd0116933d666ab35baace4d93cd400eeb0427a9179` |
| vitest-config | `https://vitest.dev/config/` | `a4fbd042aa5e885627f39dbf1869f9cd928dbdbd4abbe03f652a5bf7b3d91d48` |
| tanstack-defaults | `https://tanstack.com/query/latest/docs/framework/react/guides/important-defaults` | `13a6482b9c6f9b685ac9b2ae911d1006008d81485c83fd63830364765c5377e4` |
| tanstack-usequery | `https://tanstack.com/query/latest/docs/framework/react/reference/useQuery` | `d1aac772a6dabcb5b163c1179ede6c2a0f5fbdca0877e179b14a5275c61f8aa7` |
| react-router-declarative | `https://reactrouter.com/start/declarative/routing` | `589cffabb03b368525b24c6c572f5b14689a34f7d35ad6bfb0ade1455ea0be55` |
| openapi-typescript-cli | `https://openapi-ts.dev/cli` | `d8ef57b1f04e42b837ac326919fed380e7f22d58500413e0fb75d541eb146e12` |
| msw-node | `https://mswjs.io/docs/integrations/node` | `a56cb5d182db88b924ddbd503ae0ecae9b359c2964bff2c263d16e3bd4190dab` |
| testing-library-react | `https://testing-library.com/docs/react-testing-library/intro` | `498597e6abcb3bed7cdabe061ec262563926ebab633caa03a36139197847e377` |

## 2. Điều đã đọc từ tài liệu gốc

- **Node (lịch phát hành, ngày 2026-10-21):** `v24` — `start 2025-05-06`, `lts 2025-10-28`, `maintenance 2026-10-20`, `end 2028-04-30`, mã `Krypton`; `v26` — `start 2026-05-05`, `lts 2026-10-28` (bảy ngày sau ngày lấy); `v22` — `maintenance 2025-10-21`, `end 2027-04-30`. → **Node 24 là bản LTS đang hỗ trợ tại ngày dựng** (ADR-042). Ảnh: `node:24-trixie-slim`, digest `sha256:a6155384446670e9719bdc4fd0ebe4d4b29fb32a8d6aa523da3547a6cfbcf22c` (`NODE_VERSION=24.22.0`, đọc từ chính ảnh bằng `docker image inspect`, ngày 2026-10-21). Khi `v26` vào LTS, đổi là một quyết định riêng.
- **ESLint:** *"It should be placed in the root directory of your project and export an array of configuration objects."* với ví dụ `import { defineConfig } from "eslint/config"; export default defineConfig([ { rules: { … } } ]);` *(eslint-config)*. `no-restricted-imports`: tuỳ chọn `patterns` — *"This is also an object option whose value is an array. This option allows you to specify multiple modules to restrict using gitignore-style patterns or regular expressions."*, mỗi mẫu có `group` và `message` *(eslint-restricted-imports)*. `no-restricted-globals`: *"This rule has both string and object options"*; dạng đối tượng mang tên biến toàn cục và `message` tuỳ chọn *(eslint-restricted-globals)*. `no-restricted-properties`: cấm thuộc tính của đối tượng (`object` + `property`) *(eslint-restricted-properties)*.
- **Vite:** `server.proxy` — *"Type: Record<string, string | ProxyOptions>"* *(vite-server)*; `build.outDir` *(vite-build)*; `base` — *"Base public path when served in development or production"* *(vite-shared)*.
- **Vitest:** tuỳ chọn cấu hình `environment` *(vitest-config)*; dùng chung cấu hình Vite qua `defineConfig` của `vitest/config`.
- **TanStack Query:** *"Stale queries are refetched automatically in the background when: New instances of the query mount … The network is reconnected"*; *"you can also customize the points in time for refetches by setting options like refetchOnMount, refetchOnWindowFocus and refetchOnReconnect"*; *"Queries can optionally be configured with a refetchInterval to trigger refetches periodically, which is independent of the staleTime setting"* *(tanstack-defaults)*. `refetchInterval`: *"number | false | ((query) => number | false | undefined)"*, mặc định `false`; `refetchIntervalInBackground`: *"If set to true, the query will continue to refetch while their tab/window is in the background"*, mặc định `false` *(tanstack-usequery)*.
- **React Router:** bộ định tuyến khai báo `BrowserRouter` (và `MemoryRouter` cho test) *(react-router-declarative)*.
- **openapi-typescript:** `npx openapi-typescript schema.yaml -o schema.ts` *(openapi-typescript-cli)*.
- **MSW:** *"Import the `setupServer` function from `msw/node`"* *(msw-node)*.
- **Testing Library:** *"The more your tests resemble the way your software is used, the more confidence they can give you."* *(testing-library-react)*.

## 3. Điều chỉ biết bằng chạy thật (ghi để lần sau không phải đoán)

- **Phiên bản cài** (`package-lock.json`, ghi chính xác `--save-exact`): `react` 19.3.1, `react-dom` 19.3.1, `react-router-dom` 7.18.4, `@tanstack/react-query` 5.104.5; dev — `vite` 8.3.5, `@vitejs/plugin-react` 6.1.2, `typescript` **5.9.3**, `eslint` 10.13.0, `@eslint/js` 10.0.1, `typescript-eslint` 8.72.0, `globals` 17.13.0, `vitest` 5.0.5, `jsdom` 30.1.3, `@testing-library/react` 16.3.3, `@testing-library/dom` 10.4.2, `@testing-library/jest-dom` 7.0.1, `@testing-library/user-event` 14.6.8, `msw` 3.0.3, `openapi-typescript` 7.13.0, `@types/node` 24.19.2, `@types/react` 19.3.0, `@types/react-dom` 19.3.0.
- **TypeScript ghim 5.9.3, không phải bản mới nhất:** `npm` báo xung đột peer khi cài bản mới nhất (7.0.2): `typescript-eslint@8.72.0` đòi `typescript >=4.8.4 <6.1.0` và `openapi-typescript@7.13.0` đòi `typescript ^5.x`; 5.9.x là bản duy nhất thoả cả hai và `msw@3.0.3` (`>=5.9.x`).
- **MSW 3: tuỳ chọn xử lý request chưa có handler tên `onUnhandledFrame`** (`server.listen({ onUnhandledFrame: 'error' })`, đọc từ `shared-options.d.ts` của gói), **không phải** `onUnhandledRequest` của bản 2.x — tên cũ bị bỏ qua âm thầm.
- **`fetch` của Node không nhận đường dẫn tương đối** ở môi trường test: `api/transport/http.ts` dựng URL tuyệt đối từ `location.origin` (cùng origin như ở trình duyệt).
- **`openapi-typescript` có `exports` chặn `require.resolve` vào đường dẫn con**: `scripts/check-generated.mjs` gọi thẳng `node_modules/openapi-typescript/bin/cli.js`.
