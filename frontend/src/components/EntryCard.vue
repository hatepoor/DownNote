<script setup lang="ts">
// 条目卡（某一天的页面用）：时刻 + 完整正文 + 图片 + 心情记录行
import type { EntryItem } from '../api/client'
import { formatClock } from '../utils/time'
import CrisisMark from './CrisisMark.vue'
import MoodRecordCard from './MoodRecordCard.vue'

defineProps<{ entry: EntryItem }>()

const emit = defineEmits<{ openLightbox: [url: string] }>()
</script>

<template>
  <article class="entry">
    <time>{{ formatClock(entry.createdAt) }}</time>
    <p v-if="entry.content" class="body">{{ entry.content }}</p>
    <img
      v-if="entry.imageUrl"
      :src="entry.imageUrl"
      class="thumb"
      alt="日记配图"
      @click="emit('openLightbox', entry.imageUrl!)"
    />
    <template v-if="entry.mood">
      <MoodRecordCard :mood="entry.mood" />
      <CrisisMark v-if="entry.mood.crisis" />
    </template>
    <p v-else class="mood-pending">心情记录生成中…</p>
  </article>
</template>
