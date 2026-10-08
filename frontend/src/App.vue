<script setup lang="ts">
// 应用骨架：窄栏 + 主区域（工作台：日记 + 对话，可拖拽分栏；记忆页）+ 抽屉 + 配置弹窗。
import { onMounted, onUnmounted, ref } from 'vue'

import { fetchEntries } from './api'
import ChatPanel from './components/chat/ChatPanel.vue'
import DegradedBanner from './components/shell/DegradedBanner.vue'
import DiaryHistoryDrawer from './components/diary/DiaryHistoryDrawer.vue'
import DiaryPanel from './components/diary/DiaryPanel.vue'
import MemoryPanel from './components/memory/MemoryPanel.vue'
import ModelConfigDialog from './components/shell/ModelConfigDialog.vue'
import OnboardingGuide from './components/shell/OnboardingGuide.vue'
import TitleBar from './components/shell/TitleBar.vue'
import { bindTitlebarSync, currentView, degraded, isShell, refreshConfig, switchView, theme, toggleTheme } from './stores/appState'
import { hasSeenOnboarding, markOnboardingDone } from './stores/onboarding'
import { todayString } from './utils/time'

const DIARY_WIDTH_DEFAULT = 504
const DIARY_WIDTH_MIN = 340
const CHAT_WIDTH_MIN = 360
const DIARY_WIDTH_KEY = 'down-note:diary-width'

const drawerOpen = ref(false)
const dialogOpen = ref(false)
const showOnboarding = ref(false)
const selectedDay = ref<string | null>(null) // null = 今天
const diaryWidth = ref(DIARY_WIDTH_DEFAULT)

let dragStartX = 0
let dragStartWidth = 0

function clampDiaryWidth(width: number): number {
  // 64 = 窄栏，9 = 分栏命中区，360 = 对话栏最小宽
  const maxWidth = Math.max(DIARY_WIDTH_MIN, window.innerWidth - 64 - 9 - CHAT_WIDTH_MIN)
  return Math.min(Math.max(width, DIARY_WIDTH_MIN), maxWidth)
}

function onDragMove(event: MouseEvent): void {
  diaryWidth.value = clampDiaryWidth(dragStartWidth + event.clientX - dragStartX)
}

function stopDrag(): void {
  document.removeEventListener('mousemove', onDragMove)
  document.removeEventListener('mouseup', stopDrag)
  document.body.style.userSelect = ''
  localStorage.setItem(DIARY_WIDTH_KEY, String(diaryWidth.value))
}

function startDrag(event: MouseEvent): void {
  dragStartX = event.clientX
  dragStartWidth = diaryWidth.value
  document.addEventListener('mousemove', onDragMove)
  document.addEventListener('mouseup', stopDrag)
  document.body.style.userSelect = 'none'
}

function resetDiaryWidth(): void {
  diaryWidth.value = clampDiaryWidth(DIARY_WIDTH_DEFAULT)
  localStorage.setItem(DIARY_WIDTH_KEY, String(diaryWidth.value))
}

// 窗口缩放（最大化/还原/拖边缘）时收回越界的日记宽度——
// 否则大窗下拖出的宽度会把对话栏（min-width:0）压到消失
function onWindowResize(): void {
  diaryWidth.value = clampDiaryWidth(diaryWidth.value)
}

function toggleMemory(): void {
  const entering = currentView.value !== 'memory'
  switchView(entering ? 'memory' : 'workbench')
  if (entering) drawerOpen.value = false // 点击优先：记忆页不叠着抽屉
}

// 点击优先：记忆页点历史 = 直接回工作台（不开抽屉）；工作台上点历史 = 开/收抽屉
function openHistory(): void {
  if (currentView.value !== 'workbench') {
    switchView('workbench')
    return
  }
  drawerOpen.value = !drawerOpen.value
}

// 点某天：无论当前在哪个视图，直接切到工作台并打开那天的日记页
function onSelectDay(day: string): void {
  selectedDay.value = day === todayString() ? null : day
  switchView('workbench')
  drawerOpen.value = false
}

// 首次启动才弹：无标记 + 没写过日记 + 还没配模型（老用户静默补写标记，不打扰）
async function maybeShowOnboarding(): Promise<void> {
  if (hasSeenOnboarding()) return
  try {
    const entries = await fetchEntries(1)
    if (entries.length > 0 || degraded.value !== true) {
      markOnboardingDone()
      return
    }
  } catch {
    return // 探测失败就不打扰
  }
  showOnboarding.value = true
}

function finishOnboarding(): void {
  markOnboardingDone()
  showOnboarding.value = false
}

onMounted(async () => {
  bindTitlebarSync()
  await refreshConfig()
  const saved = Number(localStorage.getItem(DIARY_WIDTH_KEY))
  if (saved) diaryWidth.value = clampDiaryWidth(saved)
  window.addEventListener('resize', onWindowResize)
  await maybeShowOnboarding()
})

onUnmounted(() => {
  window.removeEventListener('resize', onWindowResize)
})
</script>

<template>
  <div class="app-shell">
    <TitleBar v-if="isShell" />
    <div class="grain" aria-hidden="true"></div>
    <div class="app">
      <aside class="rail">
        <div class="seal">低</div>
      <button
        class="rail-item"
        :class="{ active: drawerOpen }"
        aria-label="历史日记"
        @click="openHistory"
      >
        <svg viewBox="0 0 24 24">
          <path
            d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"
          />
        </svg>
        <span>历史</span>
      </button>
      <button
        class="rail-item"
        :class="{ active: currentView === 'memory' }"
        aria-label="长期记忆"
        @click="toggleMemory"
      >
        <svg viewBox="0 0 24 24">
          <path
            d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"
          />
        </svg>
        <span>记忆</span>
      </button>
      <div class="rail-spacer" />
      <button
        class="rail-item"
        :aria-label="theme === 'dark' ? '切换到日间模式' : '切换到夜间模式'"
        @click="toggleTheme"
      >
        <svg v-if="theme === 'dark'" viewBox="0 0 24 24">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
        <svg v-else viewBox="0 0 24 24">
          <circle cx="12" cy="12" r="5" />
          <path
            d="M12 1v2 M12 21v2 M4.22 4.22l1.42 1.42 M18.36 18.36l1.42 1.42 M1 12h2 M21 12h2 M4.22 19.78l1.42-1.42 M18.36 5.64l1.42-1.42"
          />
        </svg>
        <span>{{ theme === 'dark' ? '夜' : '日' }}</span>
      </button>
      <button class="rail-item" aria-label="设置" @click="dialogOpen = true">
        <svg viewBox="0 0 24 24">
          <circle cx="12" cy="12" r="3" />
          <path
            d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h.08a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h.08a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v.08a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"
          />
        </svg>
        <span>设置</span>
      </button>
    </aside>

    <div class="main">
      <DegradedBanner @open-settings="dialogOpen = true" />
      <div class="views">
        <!-- 两个视图叠在同一网格单元（见 layout.css .views）：切换时交叉淡化；
             工作台 v-show 保状态——翻记忆页时对话流、回顾事件都不中断 -->
        <Transition name="view-fade">
          <div
            v-show="currentView === 'workbench'"
            class="views-workbench"
            :style="{ '--diary-width': `${diaryWidth}px` }"
          >
            <DiaryPanel :day="selectedDay" @back="selectedDay = null" />
            <div
              class="sash"
              role="separator"
              aria-label="拖动调整日记与对话的宽度"
              @mousedown.prevent="startDrag"
              @dblclick="resetDiaryWidth"
            />
            <ChatPanel @open-settings="dialogOpen = true" />
          </div>
        </Transition>
        <Transition name="view-fade">
          <MemoryPanel v-show="currentView === 'memory'" />
        </Transition>
      </div>
    </div>

    <DiaryHistoryDrawer v-model:open="drawerOpen" @select-day="onSelectDay" />
    <Transition name="ink">
      <ModelConfigDialog
        v-if="dialogOpen"
        @close="dialogOpen = false"
        @saved="refreshConfig"
      />
    </Transition>
    <Transition name="ink">
      <OnboardingGuide
        v-if="showOnboarding"
        @done="finishOnboarding"
        @open-settings="dialogOpen = true"
      />
    </Transition>
  </div>
  </div>
</template>
