// HTTP 基座：后端基址解析、统一请求入口与图片地址拼接。

// API 基址：Tauri 壳下后端跑在壳分配的随机端口上（invoke 读取）；浏览器/Vite 走相对路径（Vite 代理）。
let baseCache: string | null = null

export async function apiBase(): Promise<string> {
  if (baseCache !== null) return baseCache
  if (!('__TAURI_INTERNALS__' in window)) {
    baseCache = ''
    return baseCache
  }
  const { invoke } = await import('@tauri-apps/api/core')
  for (let attempt = 0; attempt < 100; attempt += 1) {
    const port = await invoke<number | null>('backend_port')
    if (port) {
      baseCache = `http://127.0.0.1:${port}`
      return baseCache
    }
    await new Promise((resolve) => setTimeout(resolve, 300))
  }
  throw new Error('后端服务未就绪')
}

// 统一请求入口：所有 /api 调用都经它拼上基址
export async function api(path: string, init?: RequestInit): Promise<Response> {
  return fetch(`${await apiBase()}${path}`, init)
}

// 条目的图片地址：后端给的是相对路径，壳下要拼后端基址
export async function withImageBase<T extends { imageUrl: string | null }>(entry: T): Promise<T> {
  const base = await apiBase()
  return { ...entry, imageUrl: entry.imageUrl ? `${base}${entry.imageUrl}` : null }
}

export async function apiHealth(): Promise<boolean> {
  const res = await api('/api/health')
  return res.ok
}
