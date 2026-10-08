// 全局应用状态（组合式单例，不引 Pinia）：
// 模型配置 / 降级标志 / 当前视图 / 长期记忆缓存 / 日夜主题。
export {}

import { computed, ref } from 'vue'

import { fetchMemories, fetchModelSettings, type MemoryItem } from '../api'

export type AppView = 'workbench' | 'memory'
export type AppTheme = 'light' | 'dark'

// 运行环境：Tauri 壳（打包版 / tauri dev）为 true；纯浏览器 / Vite 开发为 false
export const isTauri = '__TAURI_INTERNALS__' in window

// pywebview（开发态无边框窗口）注入的桥：主题同步 + 标题栏按钮。
// 注意：这个对象页面加载后才注入（并伴随 pywebviewready 事件），所以用响应式标志跟踪。
type PywebviewApi = {
  setTitlebarDark?: (dark: boolean) => void
  windowAction?: (action: string) => Promise<string>
}

function readPywebviewApi(): PywebviewApi | undefined {
  return (window as unknown as { pywebview?: { api?: PywebviewApi } }).pywebview?.api
}

const shellReady = ref(Boolean(readPywebviewApi()))

// 是否需要应用自绘标题栏：Tauri 壳与开发态无边框窗口都要（浏览器里由浏览器接管）
export const isShell = computed(() => isTauri || shellReady.value)

// 窗口按钮动作：Tauri 走 Tauri API，开发态无边框窗口走 pywebview 桥（两者语义一致）
export async function windowAction(action: 'minimize' | 'toggleMaximize' | 'close'): Promise<void> {
  if (isTauri) {
    const { getCurrentWindow } = await import('@tauri-apps/api/window')
    const appWindow = getCurrentWindow()
    if (action === 'minimize') {
      await appWindow.minimize()
    } else if (action === 'toggleMaximize') {
      await appWindow.toggleMaximize()
    } else {
      await appWindow.close()
    }
    return
  }
  await readPywebviewApi()?.windowAction?.(action)
}

const THEME_KEY = 'down-note:theme'

const modelConfigured = ref<boolean | null>(null) // null = 尚未查询

const currentView = ref<AppView>('workbench')

const memories = ref<MemoryItem[]>([])
const memoriesFailed = ref(false)

const theme = ref<AppTheme>('light') // 日间=信笺 | 夜间=夜笺（token 切换，见 styles/tokens.css）

export const degraded = computed(() => modelConfigured.value === false)

export { currentView, memories, memoriesFailed, theme }

export function switchView(view: AppView): void {
  currentView.value = view
}

function applyTheme(next: AppTheme): void {
  theme.value = next
  document.documentElement.dataset.theme = next
  syncTitlebar(next)
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

// 桌面壳（Tauri 壳或 pywebview 开发窗口）下把主题同步到窗口；浏览器无此对象，静默跳过
function syncTitlebar(next: AppTheme): void {
  readPywebviewApi()?.setTitlebarDark?.(next === 'dark')
}

// 挂载后调用：立即同步一次，并兜住 pywebview 注入晚于挂载的情况（注入完成 → 标题栏出现）
export function bindTitlebarSync(): void {
  syncTitlebar(theme.value)
  window.addEventListener(
    'pywebviewready',
    () => {
      shellReady.value = Boolean(readPywebviewApi())
      syncTitlebar(theme.value)
    },
    { once: true },
  )
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
