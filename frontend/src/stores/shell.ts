// 桌面壳 adapter：运行环境检测、窗口动作、标题栏主题同步。
// Tauri 壳与 pywebview 开发窗口共用这一个 interface，调用方不需要区分两条壳。
import { computed, ref } from 'vue'

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

// 把主题同步到窗口；浏览器无此对象，静默跳过
export function setTitlebarDark(dark: boolean): void {
  readPywebviewApi()?.setTitlebarDark?.(dark)
}

// 挂载后调用：立即同步一次，并兜住 pywebview 注入晚于挂载的情况（注入完成 → 标题栏出现）。
// 主题值由调用方以 getter 传入——壳不持有应用状态，读取的永远是最新值。
export function bindTitlebarSync(readDark: () => boolean): void {
  const sync = (): void => setTitlebarDark(readDark())
  sync()
  window.addEventListener(
    'pywebviewready',
    () => {
      shellReady.value = Boolean(readPywebviewApi())
      sync()
    },
    { once: true },
  )
}
