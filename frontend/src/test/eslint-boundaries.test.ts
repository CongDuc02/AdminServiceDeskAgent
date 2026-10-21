// @vitest-environment node
// AC-1.12 (phần ESLint): chứng minh bằng MỘT VI PHẠM CỐ Ý cho từng luật ranh giới của 06-structure.md mục 10.1–10.2 — CI đỏ khi vi phạm; và ca hợp lệ đối chứng không bị chặn.
import { join } from 'node:path'
import { ESLint } from 'eslint'
import { beforeAll, describe, expect, it } from 'vitest'

let eslint: ESLint
beforeAll(() => {
  eslint = new ESLint({ cwd: process.cwd() })
})

async function rules(file: string, code: string): Promise<string[]> {
  const [result] = await eslint.lintText(code, { filePath: join(process.cwd(), file) })
  return (result?.messages ?? []).filter((m) => m.ruleId === 'no-restricted-globals' || m.ruleId === 'no-restricted-properties' || m.ruleId === 'no-restricted-imports').map((m) => m.ruleId!)
}

const USE_FETCH = `export const a = () => fetch('/api/v1/me')\n`
const USE_EVENTSOURCE = `export const a = () => new EventSource('/api/v1/signals')\n`
const imp = (spec: string) => `import x from '${spec}'\nexport const a = x\n`

describe('fetch và EventSource', () => {
  it('fetch ngoài http.ts bị chặn (mọi thư mục)', async () => {
    for (const file of ['src/features/chat/x.ts', 'src/auth/x.ts', 'src/components/x.tsx', 'src/app/x.ts', 'src/api/endpoints/x.ts', 'src/signals/x.ts']) {
      expect(await rules(file, USE_FETCH), file).toContain('no-restricted-globals')
    }
  })
  it('window.fetch và globalThis.fetch cũng bị chặn', async () => {
    expect(await rules('src/features/chat/x.ts', `export const a = () => window.fetch('/x')\n`)).toContain('no-restricted-properties')
    expect(await rules('src/features/chat/x.ts', `export const a = () => globalThis.fetch('/x')\n`)).toContain('no-restricted-properties')
  })
  it('fetch trong api/transport/http.ts được; EventSource ở đó thì không', async () => {
    expect(await rules('src/api/transport/http.ts', USE_FETCH)).toEqual([])
    expect(await rules('src/api/transport/http.ts', USE_EVENTSOURCE)).toContain('no-restricted-globals')
  })
  it('EventSource trong api/transport/signalSource.ts được; fetch ở đó thì không; ngoài nó thì không', async () => {
    expect(await rules('src/api/transport/signalSource.ts', USE_EVENTSOURCE)).toEqual([])
    expect(await rules('src/api/transport/signalSource.ts', USE_FETCH)).toContain('no-restricted-globals')
    expect(await rules('src/features/chat/x.ts', USE_EVENTSOURCE)).toContain('no-restricted-globals')
    expect(await rules('src/api/transport/sse.ts', USE_FETCH)).toContain('no-restricted-globals')
  })
})

describe('components không biết nghiệp vụ', () => {
  it.each(['@/features/chat/useChat', '@/api/endpoints/auth', '@/api/transport/http', '@/api/queryKeys', '@/signals/x', '@/auth/useMe', '@/app/App'])('components import %s bị chặn', async (spec) => {
    expect(await rules('src/components/x.tsx', imp(spec))).toContain('no-restricted-imports')
  })
  it('components import chính components được', async () => {
    expect(await rules('src/components/x.tsx', imp('@/components/ui.module.css'))).toEqual([])
  })
})

describe('features', () => {
  it('features/<x> import api/transport bị chặn', async () => {
    expect(await rules('src/features/my-requests/x.ts', imp('@/api/transport/http'))).toContain('no-restricted-imports')
    expect(await rules('src/features/my-requests/x.ts', imp('@/api/transport/sse'))).toContain('no-restricted-imports')
  })
  it('features/chat/turnStream.ts được import http và sse — nhưng không signalSource', async () => {
    expect(await rules('src/features/chat/turnStream.ts', imp('@/api/transport/http'))).toEqual([])
    expect(await rules('src/features/chat/turnStream.ts', imp('@/api/transport/sse'))).toEqual([])
    expect(await rules('src/features/chat/turnStream.ts', imp('@/api/transport/signalSource'))).toContain('no-restricted-imports')
  })
  it('ngoại lệ chỉ của turnStream.ts: file khác của features/chat vẫn bị chặn', async () => {
    expect(await rules('src/features/chat/useChat.ts', imp('@/api/transport/http'))).toContain('no-restricted-imports')
  })
  it('features/<x> import features/<y> bị chặn (cả hai dạng đường dẫn), import của chính mình được', async () => {
    expect(await rules('src/features/chat/x.ts', imp('@/features/my-requests/useMyRequests'))).toContain('no-restricted-imports')
    expect(await rules('src/features/my-requests/x.ts', imp('@/features/chat'))).toContain('no-restricted-imports')
    expect(await rules('src/features/chat/x.ts', imp('@/features/chat/useChat'))).toEqual([])
  })
  it('features/<x> import api/endpoints, api/queryKeys, api/errors, auth, components được', async () => {
    for (const spec of ['@/api/endpoints/requests', '@/api/queryKeys', '@/api/errors', '@/auth', '@/components/Loading']) expect(await rules('src/features/chat/x.ts', imp(spec)), spec).toEqual([])
  })
  it('features không import signals hay app', async () => {
    expect(await rules('src/features/chat/x.ts', imp('@/signals/x'))).toContain('no-restricted-imports')
    expect(await rules('src/features/chat/x.ts', imp('@/app/App'))).toContain('no-restricted-imports')
  })
})

describe('api, signals, auth', () => {
  it('api/transport chỉ được import api/generated', async () => {
    for (const spec of ['@/features/chat/x', '@/auth/useMe', '@/components/Loading', '@/api/endpoints/auth', '@/api/queryKeys', '@/api/errors']) expect(await rules('src/api/transport/http.ts', imp(spec)), spec).toContain('no-restricted-imports')
    expect(await rules('src/api/transport/http.ts', imp('@/api/generated/openapi'))).toEqual([])
  })
  it('api/endpoints không import features, signals, auth, components', async () => {
    for (const spec of ['@/features/chat/x', '@/signals/x', '@/auth/useMe', '@/components/Loading']) expect(await rules('src/api/endpoints/x.ts', imp(spec)), spec).toContain('no-restricted-imports')
    expect(await rules('src/api/endpoints/x.ts', imp('@/api/transport/http'))).toEqual([])
  })
  it('signals không import features hay api/endpoints', async () => {
    expect(await rules('src/signals/x.ts', imp('@/features/chat/x'))).toContain('no-restricted-imports')
    expect(await rules('src/signals/x.ts', imp('@/api/endpoints/auth'))).toContain('no-restricted-imports')
    expect(await rules('src/signals/x.ts', imp('@/api/queryKeys'))).toEqual([])
    expect(await rules('src/signals/x.ts', imp('@/api/transport/signalSource'))).toEqual([])
  })
  it('auth không import features hay api/transport', async () => {
    expect(await rules('src/auth/x.ts', imp('@/features/chat/x'))).toContain('no-restricted-imports')
    expect(await rules('src/auth/x.ts', imp('@/api/transport/http'))).toContain('no-restricted-imports')
    expect(await rules('src/auth/x.ts', imp('@/api/endpoints/auth'))).toEqual([])
  })
})

describe('đường dẫn tương đối không lách được luật', () => {
  it('import "../" bị chặn ở mọi nơi; "./" được', async () => {
    expect(await rules('src/components/x.tsx', imp('../features/chat/useChat'))).toContain('no-restricted-imports')
    expect(await rules('src/features/chat/x.ts', imp('../my-requests/useMyRequests'))).toContain('no-restricted-imports')
    expect(await rules('src/auth/x.ts', imp('../api/transport/http'))).toContain('no-restricted-imports')
    expect(await rules('src/features/chat/x.ts', imp('./useChat'))).toEqual([])
  })
})
