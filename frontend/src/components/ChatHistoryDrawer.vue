<script setup lang="ts">
// 会话历史抽屉：右侧 320px 滑出；列表项 = 日期 + 首条用户消息摘要；点击载入续聊。
import { ref, watch } from 'vue'

import { fetchChatSessions, type ChatSessionItem } from '../api/client'

// defineModel 必须显式命名为 'open'——与父组件的 v-model:open 对应；
// 不带名字时是 modelValue（裸 v-model），父组件的状态传不进来（已踩坑验证）
const open = defineModel<boolean>('open', { default: false })

defineProps<{ current: string | null }>()

const emit = defineEmits<{ select: [sessionId: string] }>()

const sessions = ref<ChatSessionItem[]>([])
const loading = ref(false)

watch(open, async (isOpen) => {
  if (!isOpen) return
  loading.value = true
  try {
    sessions.value = await fetchChatSessions()
  } finally {
    loading.value = false
  }
})

function pick(sessionId: string): void {
  emit('select', sessionId)
  open.value = false
}
</script>

<template>
  <div class="scrim" :class="{ open }" @click="open = false" />
  <aside class="chat-drawer" :class="{ open }" aria-label="历史会话">
    <div class="d-head">
      <h2>历史会话</h2>
      <button class="d-close" aria-label="关闭历史会话" @click="open = false">✕</button>
    </div>
    <div class="d-list">
      <p v-if="!loading && sessions.length === 0" class="d-empty">
        <span class="main">还没有对话。</span>
        <span class="sub">写点什么，或直接唤醒它</span>
      </p>
      <button
        v-for="s in sessions"
        :key="s.sessionId"
        class="session-item"
        :class="{ active: s.sessionId === current }"
        @click="pick(s.sessionId)"
      >
        <time>{{ s.startedAt.replace('T', ' ').slice(0, 16) }}</time>
        <p class="preview">{{ s.preview }}</p>
      </button>
    </div>
  </aside>
</template>
