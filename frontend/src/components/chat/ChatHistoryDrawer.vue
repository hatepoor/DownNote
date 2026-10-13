<script setup lang="ts">
// 会话历史抽屉：右侧 320px 滑出；列表项 = 日期 + 首条用户消息摘要；点击载入续聊。
// v0.2.0 03：每条会话可删——就地二次确认，删的是这次对话本身，不可恢复。
import { ref, watch } from 'vue'

import { deleteChatSession, fetchChatSessions, type ChatSessionItem } from '../../api'

// defineModel 必须显式命名为 'open'——与父组件的 v-model:open 对应；
// 不带名字时是 modelValue（裸 v-model），父组件的状态传不进来（已踩坑验证）
const open = defineModel<boolean>('open', { default: false })

defineProps<{ current: string | null }>()

const emit = defineEmits<{ select: [sessionId: string]; delete: [sessionId: string] }>()

const sessions = ref<ChatSessionItem[]>([])
const loading = ref(false)
const pendingDelete = ref<string | null>(null)
const deleting = ref(false)
const errorMessage = ref('')

watch(open, async (isOpen) => {
  if (!isOpen) return
  pendingDelete.value = null
  await refresh()
})

async function refresh(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    sessions.value = await fetchChatSessions()
  } catch {
    errorMessage.value = '列表读取失败，稍后再试'
  } finally {
    loading.value = false
  }
}

function pick(sessionId: string): void {
  emit('select', sessionId)
  open.value = false
}

function askDelete(sessionId: string): void {
  pendingDelete.value = sessionId
  errorMessage.value = ''
}

async function confirmDelete(sessionId: string): Promise<void> {
  deleting.value = true
  errorMessage.value = ''
  try {
    await deleteChatSession(sessionId)
    pendingDelete.value = null
    await refresh()
    emit('delete', sessionId)
  } catch (e) {
    errorMessage.value = e instanceof Error ? e.message : '删除失败，可重试'
  } finally {
    deleting.value = false
  }
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
      <div v-for="s in sessions" :key="s.sessionId" class="session-row">
        <div v-if="pendingDelete === s.sessionId" class="del-confirm">
          <p class="del-text">删除后不可恢复，这次对话就没了。</p>
          <div class="del-btns">
            <button class="del-cancel" type="button" :disabled="deleting" @click="pendingDelete = null">
              取消
            </button>
            <button
              class="del-ok"
              type="button"
              :disabled="deleting"
              @click="confirmDelete(s.sessionId)"
            >
              {{ deleting ? '删除中…' : '删除' }}
            </button>
          </div>
        </div>
        <template v-else>
          <button
            class="session-item"
            :class="{ active: s.sessionId === current }"
            @click="pick(s.sessionId)"
          >
            <time>{{ s.startedAt.replace('T', ' ').slice(0, 16) }}</time>
            <p class="preview">{{ s.preview }}</p>
          </button>
          <button class="row-delete" type="button" aria-label="删除这次对话" @click="askDelete(s.sessionId)">
            删除
          </button>
        </template>
      </div>
      <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>
    </div>
  </aside>
</template>

<style scoped>
/* 一行会话 = 条目 + 悬停露出的删除入口（删除是低频动作，不常驻视觉噪音） */
.session-row {
  position: relative;
  display: flex;
  align-items: stretch;
  gap: 0;
}
.session-row .session-item {
  flex: 1;
  min-width: 0;
}
.row-delete {
  flex: none;
  align-self: center;
  padding: 4px 2px 4px 8px;
  font-size: var(--fs-caption);
  color: var(--ink-3);
  opacity: 0;
  transition: opacity 180ms ease, color 180ms ease;
}
.session-row:hover .row-delete,
.row-delete:focus-visible {
  opacity: 1;
}
.row-delete:hover {
  color: var(--accent);
}
.del-confirm {
  flex: 1;
  padding: 10px 6px;
  border-top: 1px solid var(--hairline);
  border-bottom: 1px solid var(--hairline);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.del-text {
  font-size: var(--fs-caption);
  color: var(--ink-2);
}
.del-btns {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.del-cancel,
.del-ok {
  font-size: var(--fs-caption);
  letter-spacing: 1px;
  padding: 4px 12px;
  border-radius: 2px;
}
.del-cancel {
  border: 1px solid var(--hairline-strong);
  color: var(--ink-2);
}
.del-ok {
  background: var(--accent-fill);
  color: var(--on-accent);
}
.del-ok:disabled,
.del-cancel:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
