// 历史日记接口：按天分页与单日详情。
import { api, withImageBase } from './http'
import type { DiaryDayDetail, DiaryDayItem } from './types'

export async function fetchDiaryDays(limit = 20, offset = 0): Promise<DiaryDayItem[]> {
  const res = await api(`/api/diaries?limit=${limit}&offset=${offset}`)
  if (!res.ok) throw new Error('拉取历史失败')
  return res.json()
}

export async function fetchDayDetail(day: string): Promise<DiaryDayDetail> {
  const res = await api(`/api/diaries/${day}`)
  if (!res.ok) throw new Error('拉取这天的日记失败')
  const detail: DiaryDayDetail = await res.json()
  const [digest, entries] = await Promise.all([
    detail.digest ? withImageBase(detail.digest) : Promise.resolve(null),
    Promise.all(detail.entries.map(withImageBase)),
  ])
  return { ...detail, digest, entries }
}
