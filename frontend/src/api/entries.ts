// 日记条目接口：创建（文字/图片）、拉取、编辑与重新分析；分析状态走 SSE 推送。
import { api, apiBase, withImageBase } from './http'
import type { AnalyzeState, EntryItem } from './types'

export async function fetchEntries(limit = 50, offset = 0): Promise<EntryItem[]> {
  const res = await api(`/api/entries?limit=${limit}&offset=${offset}`)
  if (!res.ok) throw new Error(`拉取日记失败：${res.status}`)
  const entries: EntryItem[] = await res.json()
  return Promise.all(entries.map(withImageBase))
}

export async function submitEntry(content: string, image: File | null): Promise<EntryItem> {
  const form = new FormData()
  form.append('content', content)
  if (image) form.append('image', image)
  const res = await api('/api/entries', { method: 'POST', body: form })
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail ?? '没有记下来，再试一次')
  }
  return withImageBase(await res.json())
}

export async function updateEntry(entryId: number, content: string): Promise<EntryItem> {
  const res = await api(`/api/entries/${entryId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail ?? '没有保存，再试一次')
  }
  return withImageBase(await res.json())
}

export async function reanalyzeEntry(entryId: number): Promise<EntryItem> {
  const res = await api(`/api/entries/${entryId}/reanalyze`, { method: 'POST' })
  if (!res.ok) throw new Error('重新分析失败')
  return withImageBase(await res.json())
}

// 分析状态常驻事件流（与对话事件流同款）：心情记录完成 / 失败即时通知，无需轮询
export async function openEntryEvents(
  onEvent: (e: { type: string; entryId: number; analyzeState: AnalyzeState }) => void,
): Promise<EventSource> {
  const source = new EventSource(`${await apiBase()}/api/entries/events`)
  source.onmessage = (e) => onEvent(JSON.parse(e.data))
  return source
}
