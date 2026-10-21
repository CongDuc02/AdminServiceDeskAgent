// Bộ phân tích text/event-stream: ranh giới khối, CRLF/CR/LF, nhiều dòng data, chú thích, sự kiện cụt cuối luồng.
import { describe, expect, it } from 'vitest'
import { parseSse, type SseEvent } from './sse'

function streamOf(...chunks: (string | Uint8Array)[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(typeof c === 'string' ? enc.encode(c) : c)
      controller.close()
    },
  })
}

async function collect(stream: ReadableStream<Uint8Array>): Promise<SseEvent[]> {
  const out: SseEvent[] = []
  for await (const e of parseSse(stream)) out.push(e)
  return out
}

describe('parseSse', () => {
  it('một sự kiện đầy đủ', async () => {
    expect(await collect(streamOf('event: turn.accepted\ndata: {"a":1}\n\n'))).toEqual([{ event: 'turn.accepted', data: '{"a":1}' }])
  })

  it('nhiều sự kiện liên tiếp theo thứ tự', async () => {
    const out = await collect(streamOf('event: turn.accepted\ndata: 1\n\nevent: turn.progress\ndata: 2\n\nevent: turn.reply\ndata: 3\n\n'))
    expect(out.map((e) => e.event)).toEqual(['turn.accepted', 'turn.progress', 'turn.reply'])
    expect(out.map((e) => e.data)).toEqual(['1', '2', '3'])
  })

  it('cắt khối ở mọi vị trí vẫn ra đúng', async () => {
    const full = 'event: turn.reply\ndata: {"b":"xin chào"}\n\nevent: x\ndata: y\n\n'
    const bytes = new TextEncoder().encode(full)
    for (let cut = 1; cut < bytes.length; cut++) {
      const out = await collect(streamOf(bytes.slice(0, cut), bytes.slice(cut)))
      expect(out, `cắt ở ${cut}`).toEqual([{ event: 'turn.reply', data: '{"b":"xin chào"}' }, { event: 'x', data: 'y' }])
    }
  })

  it('CRLF, CR đơn và LF; CRLF bị chia đôi giữa hai khối', async () => {
    expect(await collect(streamOf('event: a\r\ndata: 1\r\n\r\n'))).toEqual([{ event: 'a', data: '1' }])
    expect(await collect(streamOf('event: a\rdata: 1\r\r'))).toEqual([{ event: 'a', data: '1' }])
    expect(await collect(streamOf('event: a\r', '\ndata: 1\r', '\n\r', '\n'))).toEqual([{ event: 'a', data: '1' }])
  })

  it('nhiều dòng data nối bằng LF; một dấu cách sau ":" bị bỏ, dấu cách thứ hai giữ nguyên', async () => {
    expect(await collect(streamOf('data: dòng 1\ndata:  dòng 2\n\n'))).toEqual([{ event: 'message', data: 'dòng 1\n dòng 2' }])
  })

  it('chú thích và field lạ bị bỏ; sự kiện không có data bị bỏ', async () => {
    expect(await collect(streamOf(': giữ kết nối\n\nretry: 1000\nid: 7\nevent: a\ndata: 1\n\nevent: rỗng\n\n'))).toEqual([{ event: 'a', data: '1' }])
  })

  it('ký tự đa byte bị cắt giữa chừng giữa hai khối', async () => {
    const bytes = new TextEncoder().encode('event: a\ndata: Việt Nam — “giả”\n\n')
    const out = await collect(streamOf(bytes.slice(0, 20), bytes.slice(20, 23), bytes.slice(23)))
    expect(out).toEqual([{ event: 'a', data: 'Việt Nam — “giả”' }])
  })

  it('sự kiện chưa được chốt bằng dòng trống ở cuối luồng bị bỏ (stream đứt giữa sự kiện)', async () => {
    expect(await collect(streamOf('event: turn.reply\ndata: {"dở'))).toEqual([])
    expect(await collect(streamOf('event: a\ndata: 1\n\nevent: b\ndata: dở'))).toEqual([{ event: 'a', data: '1' }])
  })

  it('luồng rỗng → không sự kiện', async () => {
    expect(await collect(streamOf())).toEqual([])
  })
})
