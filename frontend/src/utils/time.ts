// 时间展示工具：条目时间与面板头日期（见 front_design/03-布局与页面.md）
const WEEKDAYS = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT']

function pad(n: number): string {
  return String(n).padStart(2, '0')
}

function dateKey(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function isToday(iso: string): boolean {
  return iso.slice(0, 10) === dateKey(new Date())
}

function hhmm(d: Date): string {
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// 条目时间：今天→HH:MM；昨天→昨天 · HH:MM；更早→M月D日 · HH:MM
export function formatEntryTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  if (isToday(iso)) return hhmm(d)
  const now = new Date()
  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  if (dateKey(d) === dateKey(yesterday)) return `昨天 · ${hhmm(d)}`
  return `${d.getMonth() + 1}月${d.getDate()}日 · ${hhmm(d)}`
}

// 面板头日期：2026.10.05 MON
export function formatPanelDate(): string {
  const d = new Date()
  return `${d.getFullYear()}.${pad(d.getMonth() + 1)}.${pad(d.getDate())} ${WEEKDAYS[d.getDay()]}`
}

const WEEKDAY_CN = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

// 今天日期串（本地时区 YYYY-MM-DD），用于按天查询与比较
export function todayString(): string {
  return dateKey(new Date())
}

// 某天（YYYY-MM-DD）的标题：2026/10/5 周一（一律具体日期，不用"今天/昨天"）
export function formatDayTitle(day: string): string {
  const d = new Date(`${day}T00:00:00`)
  if (Number.isNaN(d.getTime())) return day
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()} ${WEEKDAY_CN[d.getDay()]}`
}

// 条目时刻：只取 HH:MM（所在页面的标题已有日期）
export function formatClock(iso: string): string {
  return iso.length >= 16 ? iso.slice(11, 16) : iso
}
