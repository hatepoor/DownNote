// 系统通知桥：订阅"主动开口"通知通道 → 弹系统通知 → 窗口被唤起时打开绑定的会话。
//
// 为什么不是"点击通知回调"：Windows 桌面通知没有点击回调（tauri-plugin-notification 的
// 行动事件只有移动端支持），系统走的是原生"点击即激活应用"。所以把"被通知的会话"先记下来，
// 窗口一获得焦点就打开它——效果等同"点通知回到那条会话"。
// 注意：开发态（target/debug）通知不带应用身份（AUMID），"点击 toast 唤起"归打包态验证。
import { openNotifyEvents, type NotifyEvent } from '../api'
import { isTauri } from './shell'
import { markPendingSession, requestOpenSession, takePendingSession } from './appState'

const PENDING_TTL_MS = 10 * 60 * 1000 // 超时不再抢焦点：之后手动开窗不跳会话

let started = false

async function deliver(e: NotifyEvent): Promise<void> {
  const { isPermissionGranted, requestPermission, sendNotification } = await import(
    '@tauri-apps/plugin-notification'
  )
  const granted = (await isPermissionGranted()) || (await requestPermission()) === 'granted'
  if (!granted) return // 被拒就静默：消息仍落在会话里，只是没有提醒
  sendNotification({ title: e.title, body: e.body })
  markPendingSession(e.sessionId)
}

function consumePending(): void {
  const sessionId = takePendingSession(PENDING_TTL_MS)
  if (sessionId) requestOpenSession(sessionId)
}

export async function startNotifyBridge(): Promise<void> {
  if (started) return
  started = true
  if (isTauri) {
    const { getCurrentWindow } = await import('@tauri-apps/api/window')
    await getCurrentWindow().onFocusChanged(({ payload: focused }) => {
      if (focused) consumePending()
    })
  }
  await openNotifyEvents((e) => {
    if (e.type !== 'notify' || !isTauri) return
    if (document.hasFocus()) return // 窗口在前台：消息直接进会话，不打扰
    void deliver(e)
  })
}
