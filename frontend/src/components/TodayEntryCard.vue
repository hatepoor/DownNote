<script setup lang="ts">
// 今天条目卡：时刻 + 正文（3 行截断，点击展开）+ 心情记录行。
// 展开后的「编辑」不在此处改，而是把内容交给上方主编辑器（同一篇，id 不变）。
// 动效：新条目落印（fresh 由 DiaryPanel 判定，首帧不落）；心情记录行等到抵达时落印。
import { ref, watch } from 'vue'

import type { EntryItem } from '../api/client'
import { formatEntryTime } from '../utils/time'
import CrisisMark from './CrisisMark.vue'
import MoodRecordCard from './MoodRecordCard.vue'

const props = defineProps<{ entry: EntryItem; fresh?: boolean }>()

const emit = defineEmits<{ edit: [entry: EntryItem] }>()

const expanded = ref(false)

// 从"生成中"到心情记录抵达的那一刻落印一次（初始就有记录时不放）
const moodStamped = ref(false)
watch(
  () => props.entry.mood,
  (mood, previous) => {
    if (mood && !previous) moodStamped.value = true
  },
)

function toggle(): void {
  expanded.value = !expanded.value
}

function startEdit(): void {
  expanded.value = false // 收回卡片，注意力给到上方编辑器
  emit('edit', props.entry)
}
</script>

<template>
  <article class="entry" :class="{ 'stamp-entry': fresh }">
    <time>{{ formatEntryTime(entry.createdAt) }}</time>
    <p
      v-if="entry.content"
      class="body"
      :class="{ clamp3: !expanded }"
      @click="toggle"
    >
      {{ entry.content }}
    </p>
    <div v-if="expanded" class="entry-ops">
      <button class="m-link" @click="startEdit">编辑</button>
      <button class="m-link" @click="expanded = false">收起</button>
    </div>
    <template v-if="entry.mood">
      <div class="mood-block" :class="{ 'stamp-mood': moodStamped }">
        <MoodRecordCard :mood="entry.mood" />
        <CrisisMark v-if="entry.mood.crisis" />
      </div>
    </template>
    <p v-else class="mood-pending">心情记录生成中…</p>
  </article>
</template>

<style scoped>
.body {
  cursor: pointer;
}
</style>
