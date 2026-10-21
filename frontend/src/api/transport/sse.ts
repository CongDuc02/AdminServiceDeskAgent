// Phân tích `text/event-stream` của stream lượt chat (05-api.md mục 3.1; ADR-018). Chỉ đọc luồng byte — không biết sự kiện nào có nghĩa gì.
// Chuẩn: dòng kết thúc bằng LF, CR hoặc CRLF; dòng trống chốt một sự kiện; dòng bắt đầu bằng ":" là chú thích; "field: value" (một dấu cách sau ":" bị bỏ);
// nhiều dòng `data:` nối bằng LF; sự kiện không có `data` bị bỏ.

export type SseEvent = { event: string; data: string }

export async function* parseSse(stream: ReadableStream<Uint8Array>): AsyncGenerator<SseEvent> {
  const reader = stream.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let eventName = ''
  let dataLines: string[] = []

  const dispatch = (): SseEvent | null => {
    const out = dataLines.length > 0 ? { event: eventName || 'message', data: dataLines.join('\n') } : null
    eventName = ''
    dataLines = []
    return out
  }

  const line = (raw: string): SseEvent | null => {
    if (raw === '') return dispatch()
    if (raw.startsWith(':')) return null
    const colon = raw.indexOf(':')
    const field = colon === -1 ? raw : raw.slice(0, colon)
    let value = colon === -1 ? '' : raw.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'event') eventName = value
    else if (field === 'data') dataLines.push(value)
    return null
  }

  try {
    let pendingCr = false
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let start = 0
      for (let i = 0; i < buffer.length; i++) {
        const c = buffer[i]
        if (pendingCr && i === start && c === '\n') {
          start = i + 1 // LF của một CRLF bị chia làm hai khối
          pendingCr = false
          continue
        }
        pendingCr = false
        if (c === '\n' || c === '\r') {
          const event = line(buffer.slice(start, i))
          start = i + 1
          if (c === '\r') {
            if (buffer[i + 1] === '\n') {
              i++
              start = i + 1
            } else if (i + 1 === buffer.length) {
              pendingCr = true
            }
          }
          if (event) yield event
        }
      }
      buffer = buffer.slice(start)
    }
    buffer += decoder.decode()
    if (buffer !== '') {
      const event = line(buffer)
      if (event) yield event
    }
    // Chuẩn: sự kiện chưa được chốt bằng dòng trống ở cuối luồng bị bỏ — stream đứt giữa sự kiện không phát ra sự kiện cụt.
  } finally {
    reader.releaseLock()
  }
}
