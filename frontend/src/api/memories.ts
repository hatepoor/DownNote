// 长期记忆接口：增改删查；变更走 SSE 推送（智能体写入后前端即时刷新）。
import { api, apiBase } from './http'
import type { MemoryItem } from './types'

export async function fetchMemories(): Promise<MemoryItem[]> {
  const res = await api('/api/memories')
  if (!res.ok) throw new Error('拉取长期记忆失败')
  return res.json()
}

export async function createMemory(
  category: 'basic' | 'psych',
  content: string,
): Promise<MemoryItem> {
  const res = await api('/api/memories', {
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
  const res = await api(`/api/memories/${memoryId}`, {
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
  const res = await api(`/api/memories/${memoryId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('没有删掉，再试一次')
}

// 记忆变更常驻事件流（与分析状态流同款）：任何写入成功后即时通知，无需轮询
export async function openMemoryEvents(
  onEvent: (e: { type: string }) => void,
): Promise<EventSource> {
  const source = new EventSource(`${await apiBase()}/api/memories/events`)
  source.onmessage = (e) => onEvent(JSON.parse(e.data))
  return source
}
