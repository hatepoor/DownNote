<script setup lang="ts">
// 日记编辑器：文字 + 单张贴图 + 提交。
// 也承担"编辑今天的条目"（13/16 修订）：内容载入本框、保存修改（同一篇、时间刷新）或取消。
// 高度由外层 .editor-area 控制（面板内分隔栏可拖拽），文字超出时输入框内部滚动。
import { nextTick, ref, watch } from 'vue'

import { submitEntry, updateEntry, type EntryItem } from '../../api'

const props = defineProps<{ editEntry?: EntryItem | null }>()

const emit = defineEmits<{ submitted: []; editDone: []; editCancel: [] }>()

const content = ref('')
const imageFile = ref<File | null>(null)
const imagePreview = ref('')
const submitting = ref(false)
const errorMessage = ref('')
const textareaEl = ref<HTMLTextAreaElement | null>(null)

const isEditing = ref(false)
const editingId = ref<number | null>(null)
const editingClock = ref('')

// 父组件给出 editEntry = 进入编辑；置回 null（保存/取消后）= 回到新写模式
watch(
  () => props.editEntry,
  (entry) => {
    if (entry) {
      isEditing.value = true
      editingId.value = entry.id
      editingClock.value = entry.createdAt.slice(11, 16)
      content.value = entry.content
      removeImage()
      errorMessage.value = ''
      nextTick(() => {
        textareaEl.value?.focus()
        const end = content.value.length
        textareaEl.value?.setSelectionRange(end, end)
      })
    } else {
      isEditing.value = false
      editingId.value = null
      editingClock.value = ''
      content.value = ''
    }
  },
)

function onImageChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  if (!file) return
  imageFile.value = file
  imagePreview.value = URL.createObjectURL(file)
}

function removeImage(): void {
  imageFile.value = null
  imagePreview.value = ''
}

function cancelEdit(): void {
  emit('editCancel')
}

async function submit(): Promise<void> {
  const editing = isEditing.value && editingId.value !== null
  if (submitting.value || (!content.value.trim() && !editing && !imageFile.value)) return
  submitting.value = true
  errorMessage.value = ''
  try {
    if (editing && editingId.value !== null) {
      // 同一篇：原文覆盖、时间刷新为保存时刻（后端处理），旧心情记录作废并重析
      await updateEntry(editingId.value, content.value.trim())
      emit('editDone')
    } else {
      await submitEntry(content.value, imageFile.value)
      content.value = ''
      removeImage()
      emit('submitted')
    }
  } catch (e) {
    const fallback = editing ? '没有保存，再试一次' : '没有记下来，再试一次'
    errorMessage.value = e instanceof Error ? e.message : fallback
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <!-- 信笺卡（02 §3.5 轮次03）：一张纸放在桌面上——贴图与提交收进卡内 -->
  <div class="sheet">
    <textarea
      ref="textareaEl"
      v-model="content"
      :placeholder="isEditing ? '' : '此刻的心情，写下来吧'"
    />
    <div class="sheet-foot">
      <div class="attach-slot">
        <p v-if="isEditing" class="edit-hint">正在修改 {{ editingClock }} 写下的那条日记</p>
        <label v-else-if="!imageFile" class="attach-btn">
          ＋ 贴图
          <input type="file" accept="image/jpeg,image/png" @change="onImageChange" />
        </label>
        <div v-else class="attach-preview">
          <img :src="imagePreview" alt="贴图预览" />
          <span class="name">{{ imageFile.name }}</span>
          <button class="remove" aria-label="移除贴图" @click="removeImage">✕</button>
        </div>
      </div>
      <div class="submit-row">
        <button v-if="isEditing" class="btn-cancel" @click="cancelEdit">取消</button>
        <button
          class="btn-zhu"
          :disabled="submitting || (!content.trim() && !isEditing && !imageFile)"
          @click="submit"
        >
          <template v-if="isEditing">{{ submitting ? '保存中…' : '保存修改' }}</template>
          <template v-else>{{ submitting ? '记录中…' : '记录今天' }}</template>
        </button>
      </div>
    </div>
    <p v-if="errorMessage" class="error-text sheet-error">{{ errorMessage }}</p>
  </div>
</template>
