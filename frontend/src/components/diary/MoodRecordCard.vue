<script setup lang="ts">
// 心情记录条：铅字框 chips + 强度点 + 引文式摘要（front_design/04-MoodRecordCard、02 视觉规范）
import type { MoodItem } from '../../api'
import { moodColorClass } from '../../utils/emotions'

defineProps<{ mood: MoodItem }>()
</script>

<template>
  <div class="mood">
    <span
      v-for="label in mood.labels"
      :key="label"
      class="chip"
      :class="moodColorClass(label)"
    >
      {{ label }}
    </span>
    <span class="dots" :aria-label="`情绪强度 ${mood.intensity} / 10`">
      <span class="on">{{ '●'.repeat(mood.intensity) }}</span><span class="off">{{ '○'.repeat(10 - mood.intensity) }}</span>
    </span>
  </div>
  <p v-if="mood.summary" class="summary">——{{ mood.summary }}</p>
</template>
