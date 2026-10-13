// 模型配置接口：读取与保存（三件套 + 生成参数）；v0.2.0 起追加陪伴与人格设置。
import { api } from './http'
import type { CompanionSettings, ModelSettings, PersonaSettings } from './types'

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

export async function fetchCompanionSettings(): Promise<CompanionSettings> {
  const res = await api('/api/settings/companion')
  if (!res.ok) throw new Error(`读取陪伴设置失败：${res.status}`)
  return res.json()
}

export async function saveCompanionSettings(enabled: boolean, tier: string): Promise<void> {
  const res = await api('/api/settings/companion', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled, tier }),
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail ?? `保存失败：${res.status}`)
  }
}

export async function fetchPersonaSettings(): Promise<PersonaSettings> {
  const res = await api('/api/settings/persona')
  if (!res.ok) throw new Error(`读取人格设置失败：${res.status}`)
  return res.json()
}

export async function savePersonaSettings(enabled: boolean, content: string): Promise<void> {
  const res = await api('/api/settings/persona', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled, content }),
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail ?? `保存失败：${res.status}`)
  }
}
