// 情绪标签 → 铅字框描边色（front_design/02-视觉规范.md 情绪色族）
// 标签按族归档：同族共用一色，新增标签只需挂到已有族（未登记的标签落 neutral）
const MOOD_COLOR_KEYS: Record<string, string> = {
  // 低落族
  低落: 'low',
  难过: 'low',
  失落: 'low',
  沮丧: 'low',
  空虚: 'low',
  麻木: 'low',
  // 焦虑族
  焦虑: 'anx',
  不安: 'anx',
  紧张: 'anx',
  担心: 'anx',
  慌乱: 'anx',
  // 愤怒族
  愤怒: 'angry',
  烦躁: 'angry',
  恼火: 'angry',
  不耐烦: 'angry',
  // 委屈族
  委屈: 'wronged',
  羞耻: 'wronged',
  内疚: 'wronged',
  自责: 'wronged',
  // 疲惫族
  疲惫: 'tired',
  无力: 'tired',
  倦怠: 'tired',
  耗竭: 'tired',
  // 平静族
  平静: 'calm',
  安心: 'calm',
  放松: 'calm',
  // 希望族
  希望: 'hope',
  期待: 'hope',
  欣慰: 'hope',
  满足: 'hope',
  // 孤独族
  孤独: 'lonely',
  思念: 'lonely',
  寂寞: 'lonely',
}

export function moodColorClass(label: string): string {
  return MOOD_COLOR_KEYS[label] ?? 'neutral'
}
