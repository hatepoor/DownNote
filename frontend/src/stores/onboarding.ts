// 首次启动引导的标记（07-新手引导）：完成或跳过后写 '1'，之后不再出现。
// 判定与展示在 App.vue（结合"有没有写过日记 / 有没有配过模型"）。
const ONBOARDING_KEY = 'down-note:onboarding-done'

export function hasSeenOnboarding(): boolean {
  return localStorage.getItem(ONBOARDING_KEY) === '1'
}

export function markOnboardingDone(): void {
  localStorage.setItem(ONBOARDING_KEY, '1')
}
