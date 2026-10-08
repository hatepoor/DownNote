// 后端接口统一封装：fetch 基础路径、错误处理、SSE 解析（随模块推进充实）。
// 按领域分包后，消费方统一从此入口引入。

export * from './types'
export { apiHealth } from './http'
export { fetchEntries, submitEntry, updateEntry, reanalyzeEntry, openEntryEvents } from './entries'
export { fetchModelSettings, saveModelSettings } from './settings'
export { wakeChat, sendChatMessage, openChatEvents, fetchChatHistory, fetchChatSessions } from './chat'
export { fetchMemories, createMemory, updateMemory, deleteMemory, openMemoryEvents } from './memories'
export { fetchDiaryDays, fetchDayDetail } from './diaries'
