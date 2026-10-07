<script setup lang="ts">
// 日记面板：今天（编辑器 + 今天已写）或某一天（整合日记 + 当天原文，只读）
// 对应 front_design/03 §2、front_design/05 §3.9；编辑器与列表之间的分隔栏可拖拽。
import { computed, onMounted, ref, watch } from 'vue'

import { fetchDayDetail, fetchEntries, type DiaryDayDetail, type EntryItem } from '../api/client'
import { formatDayTitle, formatPanelDate, isToday } from '../utils/time'
import { useScrollFade } from '../utils/scrollFade'
import CrisisMark from './CrisisMark.vue'
import DiaryEditor from './DiaryEditor.vue'
import EntryCard from './EntryCard.vue'
import ImageLightbox from './ImageLightbox.vue'
import MoodRecordCard from './MoodRecordCard.vue'
import TodayEntryCard from './TodayEntryCard.vue'

const props = defineProps<{ day: string | null }>()
const emit = defineEmits<{ back: [] }>()

const entries = ref<EntryItem[]>([])
const todayEntries = computed(() => entries.value.filter((e) => isToday(e.createdAt)))
const todayListEl = ref<HTMLElement | null>(null)
const dayScrollEl = ref<HTMLElement | null>(null)

// 新条目落印标记（首帧不落印——设计禁用项：首帧整体浮现）
const knownEntryIds = new Set<number>()
const freshEntryIds = ref<Set<number>>(new Set())
let baselineDone = false

useScrollFade(todayListEl)
useScrollFade(dayScrollEl)

const dayDetail = ref<DiaryDayDetail | null>(null)
const dayError = ref('')
const lightboxUrl = ref('')

const editingEntry = ref<EntryItem | null>(null) // 非空 = 主编辑器正在修改这条

async function refresh(): Promise<void> {
  const next = await fetchEntries(50)
  if (baselineDone) {
    const fresh = new Set<number>()
    for (const entry of next) {
      if (!knownEntryIds.has(entry.id)) fresh.add(entry.id)
    }
    freshEntryIds.value = fresh
    // 落印只放一次：短暂标记后清掉，避免分支重挂时重放
    window.setTimeout(() => {
      freshEntryIds.value = new Set()
    }, 1000)
  } else {
    baselineDone = true
  }
  for (const entry of next) knownEntryIds.add(entry.id)
  entries.value = next
}

async function loadDay(day: string): Promise<void> {
  dayError.value = ''
  dayDetail.value = null
  try {
    dayDetail.value = await fetchDayDetail(day)
  } catch {
    dayError.value = '没读到这天的日记，稍后再试。'
  }
}

// 提交/编辑后补拉：既析通常数秒完成；失败则等兜底扫描，不制造焦虑
function refreshSoon(): void {
  refresh()
  window.setTimeout(refresh, 6000)
}

// 主编辑器的"修改今天的条目"完成/取消：清掉编辑目标，保存后补拉列表
function onEditDone(): void {
  editingEntry.value = null
  refreshSoon()
}

watch(
  () => props.day,
  (day) => {
    if (day !== null) loadDay(day)
  },
)

onMounted(() => {
  refresh()
  if (props.day !== null) loadDay(props.day)
})
</script>

<template>
  <section class="panel-diary">
    <template v-if="day === null">
      <header class="p-head">
        <h1>今天</h1>
        <time>{{ formatPanelDate() }}</time>
      </header>
      <DiaryEditor
        :edit-entry="editingEntry"
        @submitted="refreshSoon"
        @edit-done="onEditDone"
        @edit-cancel="editingEntry = null"
      />
      <template v-if="todayEntries.length > 0">
        <p class="cap">今天已写</p>
        <div ref="todayListEl" class="today-list">
          <TodayEntryCard
            v-for="entry in todayEntries"
            :key="entry.id"
            :entry="entry"
            :fresh="freshEntryIds.has(entry.id)"
            @updated="refreshSoon"
            @edit="editingEntry = $event"
          />
        </div>
      </template>
      <p v-else class="today-empty">还没有落下字。想写的时候，随时开始。</p>
    </template>

    <template v-else>
      <header class="p-head">
        <h1>{{ formatDayTitle(day) }}</h1>
        <button class="back-today" @click="emit('back')">回到今天</button>
      </header>
      <p v-if="dayError" class="error-text">{{ dayError }}</p>
      <div v-else-if="dayDetail" ref="dayScrollEl" class="day-scroll">
        <!-- 整合日记不整篇平铺：每条原文连同各自的心情在下方按条展示，这里只放这一天整体的心情 -->
        <div v-if="dayDetail.digest" class="day-diary">
          <p class="cap">这一天的心情</p>
          <template v-if="dayDetail.digest.mood">
            <MoodRecordCard :mood="dayDetail.digest.mood" />
            <CrisisMark v-if="dayDetail.digest.mood.crisis" />
          </template>
          <p v-else class="mood-pending">心情记录生成中…</p>
        </div>
        <p v-else class="day-pending">这一天的日记还在整理中。</p>

        <template v-if="dayDetail.entries.length > 0">
          <p class="cap">这一天写下的</p>
          <div class="today-list">
            <EntryCard
              v-for="entry in dayDetail.entries"
              :key="entry.id"
              :entry="entry"
              @open-lightbox="lightboxUrl = $event"
            />
          </div>
        </template>
      </div>
      <ImageLightbox v-if="lightboxUrl" :url="lightboxUrl" @close="lightboxUrl = ''" />
    </template>
  </section>
</template>

<style scoped>
/* 今天已写：区块顶线向右收梢渐隐（条目之间的分隔仍是实线） */
.today-list {
  position: relative;
  padding-top: 16px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}
.today-list::before {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  height: 1px;
  background: linear-gradient(
    90deg,
    var(--hairline) 0%,
    var(--hairline) 76%,
    transparent 100%
  );
}
.day-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 26px;
}
.day-diary {
  display: flex;
  flex-direction: column;
  gap: 9px;
}
.day-pending {
  font-family: var(--serif);
  font-size: var(--fs-summary);
  color: var(--ink-3);
}
.back-today {
  font-size: var(--fs-caption);
  color: var(--ink-2);
  letter-spacing: 1px;
}
.back-today:hover {
  color: var(--accent);
}
</style>
