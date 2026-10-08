<script setup lang="ts">
// 长期记忆页：基本信息 / 性格画像两栏，用户可查看、编辑、删除、自行添加。
// 与智能体维护共用同一张表：谁后改谁生效，不设修改锁（CONTEXT.md「长期记忆」）。
// 刷新机制：后端推送为主（任何写入即时通知）+ 切回本页兜底刷新，推送断线也不会停留在旧列表。
import { onMounted, onUnmounted, ref, watch } from 'vue'

import { createMemory, deleteMemory, openMemoryEvents, updateMemory, type MemoryItem } from '../../api'
import { currentView, memories, memoriesFailed, refreshMemories } from '../../stores/appState'

type Category = 'basic' | 'psych'

const COLUMNS: { key: Category; title: string; hint: string; empty: string }[] = [
  {
    key: 'basic',
    title: '基本信息',
    hint: '关于你的名字、生日、生活状态。',
    empty: '它会在这里记下关于你的事，你也可以自己写下来。',
  },
  {
    key: 'psych',
    title: '性格画像',
    hint: '随着相处慢慢长出来，也可以由你亲手添一笔。',
    empty: '它会随着相处慢慢了解你。这里的一切，你都看得到、改得了。',
  },
]

const editingId = ref<number | null>(null)
const editingText = ref('')
const addingCategory = ref<Category | null>(null)
const addingText = ref('')
const confirmingId = ref<number | null>(null)
const errorText = ref('')

let memoryEvents: EventSource | null = null
let refreshTimer: number | null = null

// 事件合并：一批推送最多触发一次刷新
function scheduleRefresh(): void {
  if (refreshTimer !== null) return
  refreshTimer = window.setTimeout(() => {
    refreshTimer = null
    refreshMemories()
  }, 200)
}

// 切回记忆页兜底刷新一次：推送通道不可用时也能看到最新记忆
watch(currentView, (view) => {
  if (view === 'memory') refreshMemories()
})

onMounted(async () => {
  await refreshMemories()
  try {
    memoryEvents = await openMemoryEvents(scheduleRefresh) // EventSource 断线会自重连
  } catch {
    // 推送订阅失败：靠切页兜底刷新
  }
})

onUnmounted(() => {
  memoryEvents?.close()
  if (refreshTimer !== null) window.clearTimeout(refreshTimer)
})

function itemsOf(category: Category): MemoryItem[] {
  return memories.value.filter((memory) => memory.category === category)
}

function shortDate(iso: string): string {
  return iso.slice(5, 10)
}

function sourceLabel(memory: MemoryItem): string {
  return memory.updatedBy === 'user' ? '你写的' : '它记下的'
}

function startEdit(memory: MemoryItem): void {
  confirmingId.value = null
  addingCategory.value = null
  editingId.value = memory.id
  editingText.value = memory.content
}

function cancelEdit(): void {
  editingId.value = null
  editingText.value = ''
}

async function saveEdit(): Promise<void> {
  const content = editingText.value.trim()
  if (editingId.value === null || !content) return
  errorText.value = ''
  try {
    await updateMemory(editingId.value, content)
    cancelEdit()
    await refreshMemories()
  } catch (e) {
    errorText.value = e instanceof Error ? e.message : '没有保存，再试一次'
  }
}

async function doDelete(memoryId: number): Promise<void> {
  errorText.value = ''
  try {
    await deleteMemory(memoryId)
    confirmingId.value = null
    await refreshMemories()
  } catch (e) {
    errorText.value = e instanceof Error ? e.message : '没有删掉，再试一次'
  }
}

function startAdd(category: Category): void {
  editingId.value = null
  confirmingId.value = null
  addingCategory.value = category
  addingText.value = ''
}

function cancelAdd(): void {
  addingCategory.value = null
  addingText.value = ''
}

async function saveAdd(category: Category): Promise<void> {
  const content = addingText.value.trim()
  if (!content) return
  errorText.value = ''
  try {
    await createMemory(category, content)
    cancelAdd()
    await refreshMemories()
  } catch (e) {
    errorText.value = e instanceof Error ? e.message : '没有记下来，再试一次'
  }
}
</script>

<template>
  <section class="panel-memory">
    <header class="m-head">
      <h2>它记得的你</h2>
      <p>这里的一切，你都看得到、改得了、删得掉。</p>
    </header>

    <p v-if="errorText" class="m-error">{{ errorText }}</p>
    <p v-else-if="memoriesFailed" class="m-error">没读到记忆，稍后再打开这页看看。</p>

    <div class="m-cols">
      <div v-for="col in COLUMNS" :key="col.key" class="m-col">
        <h3>{{ col.title }}</h3>
        <p class="m-col-hint">{{ col.hint }}</p>

        <ul class="m-list">
          <li v-for="memory in itemsOf(col.key)" :key="memory.id" class="m-item">
            <template v-if="editingId === memory.id">
              <textarea v-model="editingText" class="m-edit" rows="2" />
              <div class="m-item-ops">
                <button class="m-link" @click="cancelEdit">取消</button>
                <button
                  class="btn-outline"
                  :disabled="!editingText.trim()"
                  @click="saveEdit"
                >
                  保存
                </button>
              </div>
            </template>
            <template v-else>
              <p class="m-content">{{ memory.content }}</p>
              <div class="m-item-meta">
                <span>{{ sourceLabel(memory) }} · {{ shortDate(memory.updatedAt) }}</span>
                <span class="m-item-ops">
                  <template v-if="confirmingId === memory.id">
                    <span class="m-del-hint">删掉就不会再想起来</span>
                    <button class="m-link m-link-danger" @click="doDelete(memory.id)">
                      确认删除
                    </button>
                    <button class="m-link" @click="confirmingId = null">取消</button>
                  </template>
                  <template v-else>
                    <button class="m-link" @click="startEdit(memory)">编辑</button>
                    <button class="m-link" @click="confirmingId = memory.id">删除</button>
                  </template>
                </span>
              </div>
            </template>
          </li>
          <li v-if="itemsOf(col.key).length === 0" class="m-empty">{{ col.empty }}</li>
        </ul>

        <div class="m-add">
          <template v-if="addingCategory === col.key">
            <textarea
              v-model="addingText"
              class="m-edit"
              rows="2"
              placeholder="一句话就好，比如：名字是阿澈"
            />
            <div class="m-item-ops">
              <button class="m-link" @click="cancelAdd">取消</button>
              <button class="btn-outline" :disabled="!addingText.trim()" @click="saveAdd(col.key)">
                保存
              </button>
            </div>
          </template>
          <button v-else class="m-link m-add-btn" @click="startAdd(col.key)">＋ 写一条</button>
        </div>
      </div>
    </div>
  </section>
</template>
