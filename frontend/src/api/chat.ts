// 对话接口：唤醒、发送（SSE 流式解析）与会话历史。
import { api, apiBase } from './http'
import type { ChatMessageItem, ChatSessionItem, ChatStreamEvent } from './types'

async function streamSse(res: Response, onEvent: (e: ChatStreamEvent) => void): Promise<void> {
  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''
    for (const part of parts) {
      const line = part.trim()
      if (line.startsWith('data: ')) onEvent(JSON.parse(line.slice(6)))
    }
  }
}

export async function wakeChat(onEvent: (e: ChatStreamEvent) => void): Promise<void> {
  const res = await api('/api/chat/wake', { method: 'POST' })
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail ?? '唤醒失败')
  }
  await streamSse(res, onEvent)
}

export async function sendChatMessage(
  sessionId: string,
  content: string,
  onEvent: (e: ChatStreamEvent) => void,
): Promise<void> {
  const res = await api('/api/chat/messages', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sessionId, content }),
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail ?? '发送失败')
  }
  await streamSse(res, onEvent)
}

export async function openChatEvents(
  sessionId: string,
  onEvent: (e: { type: string; message?: ChatMessageItem }) => void,
): Promise<EventSource> {
  const source = new EventSource(`${await apiBase()}/api/chat/events?sessionId=${sessionId}`)
  source.onmessage = (e) => onEvent(JSON.parse(e.data))
  return source
}

export async function fetchChatHistory(sessionId: string, afterId = 0): Promise<ChatMessageItem[]> {
  const res = await api(`/api/chat/history?sessionId=${sessionId}&afterId=${afterId}`)
  if (!res.ok) throw new Error('拉取对话失败')
  return res.json()
}

export async function fetchChatSessions(): Promise<ChatSessionItem[]> {
  const res = await api('/api/chat/sessions')
  if (!res.ok) throw new Error('拉取会话失败')
  return res.json()
}
