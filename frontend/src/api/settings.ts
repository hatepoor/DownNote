// 模型配置接口：读取与保存（三件套 + 生成参数）。
import { api } from './http'
import type { ModelSettings } from './types'

export async function fetchModelSettings(): Promise<ModelSettings> {
  const res = await api('/api/settings/model')
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
  const res = await api('/api/settings/model', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ baseUrl, modelName, apiKey, temperature, reasoningEffort }),
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail ?? `保存失败：${res.status}`)
  }
}
