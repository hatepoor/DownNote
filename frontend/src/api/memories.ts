// 长期记忆接口：增改删查。
import { api } from './http'
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
