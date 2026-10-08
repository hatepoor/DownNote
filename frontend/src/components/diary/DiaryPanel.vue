<script setup lang="ts">
// 日记面板：今天（编辑器 + 今天已写）或某一天（整合日记 + 当天原文，只读）
// 对应 front_design/03 §2、front_design/05 §3.9；编辑器与列表之间的分隔栏可拖拽。
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

import {
  fetchDayDetail,
  fetchEntries,
  openEntryEvents,
  reanalyzeEntry,
  type DiaryDayDetail,
  type EntryItem,
} from '../../api'
import { formatDayTitle, formatPanelDate, isToday } from '../../utils/time'
import { useScrollFade } from '../../utils/scrollFade'
import CrisisMark from './CrisisMark.vue'
import DiaryEditor from './DiaryEditor.vue'
import EntryCard from './EntryCard.vue'
import ImageLightbox from '../shell/ImageLightbox.vue'
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

// 分析状态靠后端推送（SSE）即时抵达；通道不可用时才退回轮询
const FALLBACK_POLL_INTERVAL_MS = 5000
const FALLBACK_POLL_MAX_MS = 120000
let entryEvents: EventSource | null = null
let refreshTimer: number | null = null
let fallbackTimer: number | null = null

function isAnalyzing(entry: EntryItem): boolean {
  return entry.analyzeState === 'pending' || entry.analyzeState === 'running'
}

// 事件合并：一批推送最多触发一次刷新
function scheduleRefresh(): void {
  if (refreshTimer !== null) return
  refreshTimer = window.setTimeout(() => {
    refreshTimer = null
    refresh()
    if (props.day !== null && dayDetail.value !== null) loadDay(props.day)
  }, 200)
}

// 兜底轮询：只在推送通道不可用时启用（5s 一次，上限 2 分钟）
function startFallbackPoll(): void {
  if (fallbackTimer !== null) return
  const deadline = Date.now() + FALLBACK_POLL_MAX_MS
  const tick = async (): Promise<void> => {
    await refresh()
    const waiting =
      entries.value.some(isAnalyzing) || (dayDetail.value?.entries.some(isAnalyzing) ?? false)
    if (waiting && Date.now() < deadline) {
      fallbackTimer = window.setTimeout(tick, FALLBACK_POLL_INTERVAL_MS)
    } else {
      fallbackTimer = null
    }
  }
  fallbackTimer = window.setTimeout(tick, FALLBACK_POLL_INTERVAL_MS)
}

async function bindAnalysisEvents(): Promise<void> {
  try {
    entryEvents = await openEntryEvents(scheduleRefresh)
    entryEvents.onerror = () => startFallbackPoll() // EventSource 会自重连；重连期间轮询兜住
  } catch {
    startFallbackPoll()
  }
}

// 提交/编辑后：立即刷一次 + 5 秒后补一次（兜住事件丢失）；分析完成由推送即时抵达
function refreshSoon(): void {
  refresh()
  window.setTimeout(refresh, 5000)
}

// 失败条目点「刷新」：请求重新分析，随后由推送（或兜底）带来新状态
async function retryAnalysis(entryId: number): Promise<void> {
  try {
    await reanalyzeEntry(entryId)
  } catch {
    return
  }
  refreshSoon()
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

onMounted(async () => {
  await refresh()
  if (props.day !== null) await loadDay(props.day)
  await bindAnalysisEvents()
  // 重开应用时若还有在分析的条目，兜底轮询保证进度可见（推送正常时它只是空转几次）
  if (entries.value.some(isAnalyzing)) startFallbackPoll()
})

onUnmounted(() => {
  entryEvents?.close()
  if (refreshTimer !== null) window.clearTimeout(refreshTimer)
  if (fallbackTimer !== null) window.clearTimeout(fallbackTimer)
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
            @retry="retryAnalysis(entry.id)"
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
          <p v-else-if="dayDetail.digest.analyzeState === 'failed'" class="mood-failed">
            分析失败
            <button class="m-link" @click="retryAnalysis(dayDetail.digest.id)">刷新</button>
          </p>
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
              @retry="retryAnalysis(entry.id)"
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
