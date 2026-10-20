// 全局应用状态（组合式单例，不引 Pinia）：
// 模型配置 / 降级标志 / 当前视图 / 长期记忆缓存 / 日夜主题 / 待打开的会话。
// 桌面壳相关（运行环境、窗口动作、标题栏）在 stores/shell.ts。
export {}

import { computed, ref } from 'vue'

import { fetchMemories, fetchModelSettings, type MemoryItem } from '../api'
import { setTitlebarDark } from './shell'

export type AppView = 'workbench' | 'memory'
export type AppTheme = 'light' | 'dark'

const THEME_KEY = 'down-note:theme'

const modelConfigured = ref<boolean | null>(null) // null = 尚未查询

const currentView = ref<AppView>('workbench')

const memories = ref<MemoryItem[]>([])
const memoriesFailed = ref(false)

const theme = ref<AppTheme>('light') // 日间=信笺 | 夜间=夜笺（token 切换，见 styles/tokens.css）

// 待打开的会话：系统通知把窗口唤起后，界面落到产生该消息的会话（见 stores/notify.ts）
export type PendingSession = { sessionId: string; requestedAt: number }

const pendingSession = ref<PendingSession | null>(null)

export const degraded = computed(() => modelConfigured.value === false)

export { currentView, memories, memoriesFailed, pendingSession, theme }

export function switchView(view: AppView): void {
  currentView.value = view
}

// 通知点击 → 打开绑定的会话：切到工作台并把会话交给对话面板载入（ChatPanel 消费后清空）
export function requestOpenSession(sessionId: string): void {
  pendingSession.value = { sessionId, requestedAt: Date.now() }
  switchView('workbench')
}

// 通知已弹出但窗口还没被唤起：先记下，等 focus 事件再决定是否打开（TTL 由 notify 判定）
export function markPendingSession(sessionId: string): void {
  pendingSession.value = { sessionId, requestedAt: Date.now() }
}

// 取出并清空待打开会话；超过 ttlMs 视为过期，不抢焦点
export function takePendingSession(ttlMs: number): string | null {
  const pending = pendingSession.value
  if (!pending) return null
  pendingSession.value = null
  return Date.now() - pending.requestedAt > ttlMs ? null : pending.sessionId
}

function applyTheme(next: AppTheme): void {
  theme.value = next
  document.documentElement.dataset.theme = next
  setTitlebarDark(next === 'dark')
}

// 挂载前调用：已选过就照旧；首次运行跟随系统偏好
export function initTheme(): void {
  const saved = localStorage.getItem(THEME_KEY)
  if (saved === 'light' || saved === 'dark') {
    applyTheme(saved)
    return
  }
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
  applyTheme(prefersDark ? 'dark' : 'light')
}

// 主题切换：整页交叉淡化（View Transitions，320ms 落墨曲线，规格见 styles/tokens.css ::view-transition-*）。
// 设计稿轮次02 曾定"即时切换"；2026-10-07 用户验收反馈日夜互换瞬时跳变刺眼，改为过渡——遮罩叠加仍是禁用项。
// 内核不支持 startViewTransition 时回退瞬时切换。
type DocumentWithViewTransition = Document & {
  startViewTransition?: (updateCallback: () => void) => unknown
}

export function toggleTheme(): void {
  const next: AppTheme = theme.value === 'dark' ? 'light' : 'dark'
  const apply = (): void => {
    localStorage.setItem(THEME_KEY, next)
    applyTheme(next)
  }
  const doc = document as DocumentWithViewTransition
  if (typeof doc.startViewTransition === 'function') {
    doc.startViewTransition(apply)
    return
  }
  apply()
}

export async function refreshConfig(): Promise<void> {
  try {
    const settings = await fetchModelSettings()
    modelConfigured.value = settings.configured
  } catch {
    modelConfigured.value = false
  }
}

export async function refreshMemories(): Promise<void> {
  memoriesFailed.value = false
  try {
    memories.value = await fetchMemories()
  } catch {
    memoriesFailed.value = true
  }
}
