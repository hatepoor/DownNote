<script setup lang="ts">
// 对话面板：唤醒/回合流式、危机资源卡、回顾事件回流、历史会话、降级态。
// 三条数据通路互不干扰：回合 SSE（POST 流）、事件通道（EventSource）、配置状态（全局 store）。
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

import {
  fetchChatHistory,
  openChatEvents,
  sendChatMessage,
  wakeChat,
  type ChatMessageItem,
  type ChatStreamEvent,
  type Hotline,
} from '../api/client'
import { degraded, refreshConfig } from '../stores/appState'
import { useScrollFade } from '../utils/scrollFade'
import ChatBubble from './ChatBubble.vue'
import ChatHistoryDrawer from './ChatHistoryDrawer.vue'
import HotlineCard from './HotlineCard.vue'

const emit = defineEmits<{ openSettings: [] }>()

const sessionId = ref<string | null>(null)
const messages = ref<ChatMessageItem[]>([])
const streamingText = ref('')
const streaming = ref(false)
const wakeNoteVisible = ref(false)
const hotlines = ref<Hotline[] | null>(null)
const turnError = ref('')
const input = ref('')
const historyOpen = ref(false)
const msgsEl = ref<HTMLElement | null>(null)

useScrollFade(msgsEl)

let eventSource: EventSource | null = null
const lastUserContent = ref('')

const canSend = computed(() => !streaming.value && !!sessionId.value && !!input.value.trim())

function handleStreamEvent(e: ChatStreamEvent): void {
  if (e.type === 'start') {
    sessionId.value = e.sessionId
    wakeNoteVisible.value = e.wakeNote === true
    openEvents()
  } else if (e.type === 'delta') {
    streamingText.value += e.text
  } else if (e.type === 'meta') {
    hotlines.value = e.hotlines
  } else if (e.type === 'done') {
    if (streamingText.value) {
      messages.value.push({
        id: Date.now(),
        role: 'assistant',
        content: streamingText.value,
        createdAt: '',
      })
      streamingText.value = ''
    }
    streaming.value = false
  } else if (e.type === 'error') {
    turnError.value = e.message
    streaming.value = false
  }
}

function openEvents(): void {
  eventSource?.close()
  eventSource = openChatEvents(sessionId.value!, (e) => {
    // 回顾结果回流：以"它"的气泡追加，不打断任何正在流式的回合
    if (e.type === 'recall' && e.message) {
      messages.value.push({ ...e.message, id: Date.now() })
      wakeNoteVisible.value = false
    }
  })
}

async function wake(): Promise<void> {
  if (degraded.value || streaming.value) return
  streaming.value = true
  turnError.value = ''
  hotlines.value = null
  messages.value = [] // 新的唤醒 = 新会话，清空当前消息流
  try {
    await wakeChat(handleStreamEvent)
    // 唤醒前输入框里已经写了话：打完招呼自动把这句话发出去，不用再点一次发送
    if (input.value.trim()) await send()
  } catch (e) {
    turnError.value = e instanceof Error ? e.message : '唤醒失败'
    streaming.value = false
  }
}

async function send(): Promise<void> {
  const content = input.value.trim()
  if (!canSend.value) return
  messages.value.push({ id: Date.now(), role: 'user', content, createdAt: '' })
  lastUserContent.value = content
  input.value = ''
  turnError.value = ''
  streaming.value = true
  try {
    await sendChatMessage(sessionId.value!, content, handleStreamEvent)
  } catch (e) {
    turnError.value = e instanceof Error ? e.message : '发送失败'
    streaming.value = false
  }
}

// 模型失联重试：仅重发最后一轮，不重复用户气泡（05 文案）
async function retry(): Promise<void> {
  if (!sessionId.value || streaming.value || !lastUserContent.value) return
  turnError.value = ''
  streaming.value = true
  try {
    await sendChatMessage(sessionId.value, lastUserContent.value, handleStreamEvent)
  } catch (e) {
    turnError.value = e instanceof Error ? e.message : '发送失败'
    streaming.value = false
  }
}

async function loadSession(id: string): Promise<void> {
  messages.value = await fetchChatHistory(id)
  sessionId.value = id
  streamingText.value = ''
  hotlines.value = null
  wakeNoteVisible.value = false
  openEvents()
}

function autoGrow(event: Event): void {
  const el = event.target as HTMLTextAreaElement
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 120)}px`
}

function onEnter(event: KeyboardEvent): void {
  if (event.shiftKey) return
  event.preventDefault()
  send()
}

watch([() => messages.value.length, streamingText], () => {
  nextTick(() => {
    const el = msgsEl.value
    if (el) el.scrollTop = el.scrollHeight
  })
})

onMounted(refreshConfig)
onUnmounted(() => eventSource?.close())
</script>

<template>
  <section class="panel-chat">
    <header class="c-head">
      <h2>对话</h2>
      <div class="c-btns">
        <button class="btn-ghost" @click="historyOpen = true">历史会话</button>
        <button class="btn-outline" :disabled="degraded || streaming" @click="wake">新的唤醒</button>
      </div>
    </header>

    <div ref="msgsEl" class="msgs">
      <div v-if="degraded" class="chat-empty">
        <p class="main">它在等一次唤醒</p>
        <p class="sub">配置好模型，它就能读着你写下的日子陪你聊</p>
        <button class="btn-outline" @click="emit('openSettings')">去配置</button>
      </div>
      <div v-else-if="!sessionId && !streaming" class="chat-empty">
        <p class="main">它在，随时可以开始</p>
        <p class="sub">唤醒后，它会先看看你最近写下的日子</p>
      </div>
      <template v-else>
        <p v-if="wakeNoteVisible" class="wake">它刚翻过你近几天的日记</p>
        <ChatBubble
          v-for="m in messages"
          :key="m.id"
          :role="m.role"
          :content="m.content"
        />
        <ChatBubble
          v-if="streamingText || streaming"
          role="assistant"
          :content="streamingText"
          streaming
        />
        <HotlineCard v-if="hotlines" :hotlines="hotlines" />
        <p v-if="turnError" class="turn-error">
          {{ turnError }}
          <button class="retry-link" @click="retry">重试</button>
        </p>
      </template>
    </div>

    <footer v-if="!degraded" class="input">
      <textarea
        class="box"
        v-model="input"
        rows="1"
        placeholder="想说点什么…"
        @input="autoGrow"
        @keydown.enter="onEnter"
      />
      <button class="btn-send" :disabled="!canSend" @click="send">发送</button>
    </footer>
    <footer v-else class="input degraded-input">
      <p class="degraded-line">
        未配置模型，仅可记录 ·
        <button class="btn-ghost" @click="emit('openSettings')">去配置</button>
      </p>
    </footer>

    <ChatHistoryDrawer v-model:open="historyOpen" :current="sessionId" @select="loadSession" />
  </section>
</template>
