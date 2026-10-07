// 情绪标签 → 铅字框描边色（front_design/02-视觉规范.md 情绪色族）
const MOOD_COLOR_KEYS: Record<string, string> = {
  低落: 'low',
  难过: 'low',
  焦虑: 'anx',
  不安: 'anx',
  愤怒: 'angry',
  烦躁: 'angry',
  委屈: 'wronged',
  疲惫: 'tired',
  无力: 'tired',
  平静: 'calm',
  安心: 'calm',
  希望: 'hope',
  期待: 'hope',
  孤独: 'lonely',
}

export function moodColorClass(label: string): string {
  return MOOD_COLOR_KEYS[label] ?? 'neutral'
}
