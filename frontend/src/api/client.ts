// 后端接口统一封装：fetch 基础路径、错误处理、SSE 解析（随模块推进充实）。
export interface MoodItem {
  labels: string[]
  intensity: number
  summary: string
  crisis: boolean
  analyzedAt: string
  model: string
}

export interface EntryItem {
  id: number
  content: string
  imageUrl: string | null
  createdAt: string
  analyzed: boolean
  kind: 'entry' | 'daily'
  mood: MoodItem | null
}

export interface ModelSettings {
  baseUrl: string
  modelName: string
  apiKeyMasked: string
  temperature: number
  reasoningEffort: string
  configured: boolean
}

export interface ChatMessageItem {
  id: number
  role: 'user' | 'assistant'
  content: string
  createdAt: string
}

export interface Hotline {
  name: string
  region: string
  phone: string
  note: string
}

export type ChatStreamEvent =
  | { type: 'start'; sessionId: string; wakeNote?: boolean }
  | { type: 'delta'; text: string }
  | { type: 'meta'; crisis: boolean; hotlines: Hotline[] }
  | { type: 'done' }
  | { type: 'error'; message: string }

export interface ChatSessionItem {
  sessionId: string
  startedAt: string
  lastActiveAt: string
  preview: string
}

export interface MemoryItem {
  id: number
  category: 'basic' | 'psych'
  content: string
  updatedBy: 'agent' | 'user'
  createdAt: string
  updatedAt: string
}

export interface DiaryDayItem {
  day: string
  entryCount: number
  digested: boolean
  preview: string
  mood: MoodItem | null
}

export interface DiaryDayDetail {
  day: string
  digest: EntryItem | null
  entries: EntryItem[]
}

export async function apiHealth(): Promise<boolean> {
  const res = await fetch('/api/health')
  return res.ok
}

export async function fetchEntries(limit = 50, offset = 0): Promise<EntryItem[]> {
  const res = await fetch(`/api/entries?limit=${limit}&offset=${offset}`)
  if (!res.ok) throw new Error(`拉取日记失败：${res.status}`)
  return res.json()
}

export async function submitEntry(content: string, image: File | null): Promise<EntryItem> {
  const form = new FormData()
  form.append('content', content)
  if (image) form.append('image', image)
  const res = await fetch('/api/entries', { method: 'POST', body: form })
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail ?? '没有记下来，再试一次')
  }
  return res.json()
}

export async function updateEntry(entryId: number, content: string): Promise<EntryItem> {
  const res = await fetch(`/api/entries/${entryId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail ?? '没有保存，再试一次')
  }
  return res.json()
}

export async function fetchModelSettings(): Promise<ModelSettings> {
  const res = await fetch('/api/settings/model')
  if (!res.ok) throw new Error(`读取配置失败：${res.status}`)
  return res.json()
}

export async function saveModelSettings(
  baseUrl: string,
  modelName: string,
  apiKey: string,
  temperature: number,
  reasoningEffort: string,
): Promise<void> {
  const res = await fetch('/api/settings/model', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ baseUrl, modelName, apiKey, temperature, reasoningEffort }),
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail ?? `保存失败：${res.status}`)
  }
}

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
  const res = await fetch('/api/chat/wake', { method: 'POST' })
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
  const res = await fetch('/api/chat/messages', {
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

export function openChatEvents(
  sessionId: string,
  onEvent: (e: { type: string; message?: ChatMessageItem }) => void,
): EventSource {
  const source = new EventSource(`/api/chat/events?sessionId=${sessionId}`)
  source.onmessage = (e) => onEvent(JSON.parse(e.data))
  return source
}

export async function fetchChatHistory(sessionId: string, afterId = 0): Promise<ChatMessageItem[]> {
  const res = await fetch(`/api/chat/history?sessionId=${sessionId}&afterId=${afterId}`)
  if (!res.ok) throw new Error('拉取对话失败')
  return res.json()
}

export async function fetchChatSessions(): Promise<ChatSessionItem[]> {
  const res = await fetch('/api/chat/sessions')
  if (!res.ok) throw new Error('拉取会话失败')
  return res.json()
}

export async function fetchMemories(): Promise<MemoryItem[]> {
  const res = await fetch('/api/memories')
  if (!res.ok) throw new Error('拉取长期记忆失败')
  return res.json()
}

export async function createMemory(
  category: 'basic' | 'psych',
  content: string,
): Promise<MemoryItem> {
  const res = await fetch('/api/memories', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ category, content }),
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail ?? '没有记下来，再试一次')
  }
  return res.json()
}

export async function updateMemory(memoryId: number, content: string): Promise<MemoryItem> {
  const res = await fetch(`/api/memories/${memoryId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail ?? '没有保存，再试一次')
  }
  return res.json()
}

export async function deleteMemory(memoryId: number): Promise<void> {
  const res = await fetch(`/api/memories/${memoryId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('没有删掉，再试一次')
}

export async function fetchDiaryDays(limit = 20, offset = 0): Promise<DiaryDayItem[]> {
  const res = await fetch(`/api/diaries?limit=${limit}&offset=${offset}`)
  if (!res.ok) throw new Error('拉取历史失败')
  return res.json()
}

export async function fetchDayDetail(day: string): Promise<DiaryDayDetail> {
  const res = await fetch(`/api/diaries/${day}`)
  if (!res.ok) throw new Error('拉取这天的日记失败')
  return res.json()
}
