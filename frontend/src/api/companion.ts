// 主动陪伴：界面活动上报（05 引擎"让路"判据的输入之一）。
// 节流：同类活动 30 秒最多报一次（后端按 5 分钟有效期判定，过期自动失效）。
import { api } from './http'

const REPORT_MIN_INTERVAL_MS = 30_000
const lastReportAt: Record<string, number> = {}

export function reportCompanionActivity(kind: 'diary' | 'chat'): void {
  const now = Date.now()
  if (now - (lastReportAt[kind] ?? 0) < REPORT_MIN_INTERVAL_MS) return
  lastReportAt[kind] = now
  void api('/api/companion/activity', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ kind }),
  }).catch(() => undefined) // 上报失败无副作用：最多是让路判据少一份输入
}
