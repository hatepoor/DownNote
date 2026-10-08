<script setup lang="ts">
// 历史日记抽屉：按天浏览（点某天 → 打开那天的日记页），滚动到底加载更早（front_design/03 §4）
import { ref, watch } from 'vue'

import { fetchDiaryDays, type DiaryDayItem } from '../../api'
import { formatDayTitle } from '../../utils/time'
import { useScrollFade } from '../../utils/scrollFade'

const PAGE_SIZE = 20

const open = defineModel<boolean>('open', { default: false })

const emit = defineEmits<{ selectDay: [day: string] }>()

const days = ref<DiaryDayItem[]>([])
const offset = ref(0)
const done = ref(false)
const loading = ref(false)
const listEl = ref<HTMLElement | null>(null)

useScrollFade(listEl)

watch(open, (isOpen) => {
  if (isOpen && days.value.length === 0) loadMore()
})

async function loadMore(): Promise<void> {
  if (loading.value || done.value) return
  loading.value = true
  try {
    const page = await fetchDiaryDays(PAGE_SIZE, offset.value)
    days.value.push(...page)
    offset.value += page.length
    if (page.length < PAGE_SIZE) done.value = true
  } finally {
    loading.value = false
  }
}

function onScroll(event: Event): void {
  const el = event.target as HTMLElement
  if (el.scrollTop + el.clientHeight >= el.scrollHeight - 24) loadMore()
}

function selectDay(day: string): void {
  emit('selectDay', day)
  open.value = false
}
</script>

<template>
  <div class="scrim" :class="{ open }" @click="open = false" />
  <aside class="drawer" :class="{ open }" aria-label="历史日记">
    <div class="d-head">
      <h2>历史日记</h2>
      <button class="d-close" aria-label="关闭历史日记" @click="open = false">✕</button>
    </div>
    <div v-if="days.length === 0 && !loading" class="d-empty">
      <p class="main">这里会收下你写下的每一天</p>
      <p class="sub">低落的日子，也值得被好好放着</p>
    </div>
    <div v-else ref="listEl" class="d-list" @scroll="onScroll">
      <button
        v-for="item in days"
        :key="item.day"
        class="d-day"
        @click="selectDay(item.day)"
      >
        <span class="d-day-date">{{ formatDayTitle(item.day) }}</span>
        <span class="d-day-preview clamp3">{{ item.preview }}</span>
        <span v-if="item.mood" class="summary">——{{ item.mood.summary }}</span>
      </button>
      <p v-if="loading" class="d-loading">加载中…</p>
    </div>
  </aside>
</template>
