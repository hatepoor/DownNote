// 通知通道：后端决定主动开口 → 推事件 → 前端弹系统通知（点击回到对应会话）。
import { apiBase } from './http'
import type { NotifyEvent } from './types'

export async function openNotifyEvents(
  onEvent: (e: NotifyEvent) => void,
): Promise<EventSource> {
  const source = new EventSource(`${await apiBase()}/api/notify/events`)
  source.onmessage = (e) => onEvent(JSON.parse(e.data))
  return source
}
