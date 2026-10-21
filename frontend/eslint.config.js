// Luật ranh giới của client — 06-structure.md mục 10.1 và 10.2, AC-1.12. CI đỏ khi vi phạm (job `frontend`); mỗi luật có test vi phạm cố ý ở src/test/eslint-boundaries.test.ts.
// Cú pháp flat config (`defineConfig` từ "eslint/config"; `no-restricted-globals` dạng {name, message}; `no-restricted-imports` dạng `patterns` + `group`) theo docs/reference/frontend-cong-cu-b10a.md.
import js from '@eslint/js'
import { defineConfig } from 'eslint/config'
import globals from 'globals'
import tseslint from 'typescript-eslint'

const FEATURES = ['all-requests', 'audit', 'chat', 'config', 'delegation', 'my-requests', 'notifications', 'review', 'revoke']

// Mọi import vượt thư mục đi qua alias `@/` — để các luật `patterns` bên dưới là kín: một import tương đối `../features/x` sẽ lách được chúng.
const NO_PARENT_RELATIVE = { group: ['../*', '../**'], message: 'Dùng alias "@/…" cho import vượt thư mục; chỉ "./…" trong cùng thư mục (luật ranh giới, 06-structure.md mục 10.1).' }

function restrict(...groups) {
  return ['error', { patterns: [NO_PARENT_RELATIVE, ...groups.map(([group, message]) => ({ group, message }))] }]
}

const noFetch = { name: 'fetch', message: 'Chỉ api/transport/http.ts được tham chiếu fetch (ADR-018). Dùng hàm của http.ts hoặc một endpoint.' }
const noEventSource = { name: 'EventSource', message: 'Chỉ api/transport/signalSource.ts được tham chiếu EventSource (ADR-018).' }
const noWindowFetch = { object: 'window', property: 'fetch', message: noFetch.message }
const noWindowEventSource = { object: 'window', property: 'EventSource', message: noEventSource.message }
const noGlobalThisFetch = { object: 'globalThis', property: 'fetch', message: noFetch.message }
const noGlobalThisEventSource = { object: 'globalThis', property: 'EventSource', message: noEventSource.message }

const restrictedProps = (...extra) => ['error', noWindowFetch, noWindowEventSource, noGlobalThisFetch, noGlobalThisEventSource, ...extra]

const otherFeatures = (x) => FEATURES.filter((y) => y !== x).map((y) => [[`@/features/${y}`, `@/features/${y}/*`], `features/${x} không được import features/${y} (mục 10.1): đưa phần dùng chung xuống components/ hoặc api/.`])

export default defineConfig([
  { ignores: ['dist', 'node_modules', 'src/api/generated'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['src/**/*.{ts,tsx}', 'vite.config.ts'],
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
    rules: {
      'no-restricted-globals': ['error', noFetch, noEventSource],
      'no-restricted-properties': restrictedProps(),
      'no-restricted-imports': restrict(),
    },
  },
  {
    // Lối fetch duy nhất: được fetch, vẫn cấm EventSource.
    files: ['src/api/transport/http.ts'],
    rules: { 'no-restricted-globals': ['error', noEventSource], 'no-restricted-properties': ['error', noWindowEventSource, noGlobalThisEventSource] },
  },
  {
    // EventSource duy nhất: được EventSource, vẫn cấm fetch.
    files: ['src/api/transport/signalSource.ts'],
    rules: { 'no-restricted-globals': ['error', noFetch], 'no-restricted-properties': ['error', noWindowFetch, noGlobalThisFetch] },
  },
  {
    files: ['src/api/transport/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': restrict(
        [['@/features/*', '@/signals/*', '@/auth/*', '@/components/*', '@/app/*', '@/api/endpoints/*', '@/api/queryKeys', '@/api/errors'], 'api/transport chỉ được import api/generated (mục 10.1).'],
      ),
    },
  },
  {
    files: ['src/api/endpoints/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': restrict(
        [['@/features/*', '@/signals/*', '@/auth/*', '@/components/*', '@/app/*'], 'api/endpoints chỉ được import api/transport/http và api/generated (mục 10.1).'],
      ),
    },
  },
  {
    files: ['src/signals/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': restrict(
        [['@/features/*', '@/api/endpoints/*', '@/api/transport/http', '@/auth/*', '@/components/*', '@/app/*'], 'signals chỉ được import api/transport/signalSource và api/queryKeys (mục 10.1).'],
      ),
    },
  },
  {
    files: ['src/auth/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': restrict(
        [['@/features/*', '@/api/transport/*', '@/signals/*', '@/app/*'], 'auth chỉ được import api/endpoints và api/queryKeys (mục 10.1).'],
      ),
    },
  },
  {
    files: ['src/components/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': restrict(
        [['@/features/*', '@/api/*', '@/signals/*', '@/auth/*', '@/app/*'], 'components là UI không biết nghiệp vụ: không import features, api, signals, auth (mục 10.1).'],
      ),
    },
  },
  ...FEATURES.map((x) => ({
    files: [`src/features/${x}/**/*.{ts,tsx}`],
    rules: {
      'no-restricted-imports': restrict(
        [['@/api/transport/*', '@/signals/*', '@/app/*'], 'features chỉ được import api/endpoints, api/queryKeys, api/errors, auth, components (mục 10.1).'],
        ...otherFeatures(x),
      ),
    },
  })),
  {
    // Ngoại lệ duy nhất của features → transport: stream lượt chat (ADR-018) — http và sse, không gì khác trong transport.
    files: ['src/features/chat/turnStream.ts'],
    rules: {
      'no-restricted-imports': restrict(
        [['@/api/transport/signalSource', '@/signals/*', '@/app/*'], 'turnStream chỉ được import api/transport/http và api/transport/sse.'],
        ...otherFeatures('chat'),
      ),
    },
  },
])
