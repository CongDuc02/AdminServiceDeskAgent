// CI đỏ nếu type sinh từ contracts/openapi.yaml lệch bản đã commit (ADR-018): sinh lại vào tệp tạm rồi so từng byte.
import { execFileSync } from 'node:child_process'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const cli = join('node_modules', 'openapi-typescript', 'bin', 'cli.js') // `exports` của gói chặn require.resolve vào đường dẫn con
const committed = 'src/api/generated/openapi.d.ts'
const dir = mkdtempSync(join(tmpdir(), 'bo19-gen-'))
const fresh = join(dir, 'openapi.d.ts')
try {
  execFileSync(process.execPath, [cli, '../docs/design/contracts/openapi.yaml', '-o', fresh], { stdio: 'ignore' })
  const a = readFileSync(committed, 'utf8').replace(/\r\n/g, '\n')
  const b = readFileSync(fresh, 'utf8').replace(/\r\n/g, '\n')
  if (a !== b) {
    console.error('LỆCH: src/api/generated/openapi.d.ts khác bản sinh lại từ openapi.yaml. Chạy `npm run gen:api` rồi commit.')
    process.exit(1)
  }
  console.log('Type sinh từ openapi.yaml khớp bản đã commit.')
} finally {
  rmSync(dir, { recursive: true, force: true })
}
