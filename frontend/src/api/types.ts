// 后端接口的请求/响应类型（与后端 api 读模型一一对应）。
export type AnalyzeState = 'pending' | 'running' | 'failed' | 'done'

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
  analyzeState: AnalyzeState
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
