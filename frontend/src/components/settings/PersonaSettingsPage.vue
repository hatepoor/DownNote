<script setup lang="ts">
// 设置 · 人格页：开关（默认关闭）+ 自定义内容（存数据目录 soul.md）。
// 手动保存（避免对话读到写到一半的文本）；留空则使用它自带的样子；可展开查看默认人格（只读预览）。
import { computed, onMounted, ref } from 'vue'

import { fetchPersonaSettings, savePersonaSettings } from '../../api'
import ToggleSwitch from '../shell/ToggleSwitch.vue'

const enabled = ref(false)
const content = ref('')
const defaultPersona = ref('')
const maxLength = ref(2000)
const saving = ref(false)
const loading = ref(false)
const hint = ref('')
const errorMessage = ref('')
const showDefault = ref(false)

const usedLength = computed(() => content.value.trim().length)
const overLimit = computed(() => usedLength.value > maxLength.value)

onMounted(async () => {
  loading.value = true
  try {
    const settings = await fetchPersonaSettings()
    enabled.value = settings.enabled
    content.value = settings.content
    defaultPersona.value = settings.defaultPersona
    maxLength.value = settings.maxLength
  } catch {
    errorMessage.value = '读取人格设置失败'
  } finally {
    loading.value = false
  }
})

async function save(): Promise<void> {
  if (overLimit.value) {
    errorMessage.value = `最多 ${maxLength.value} 字，请精简后再保存`
    return
  }
  saving.value = true
  hint.value = ''
  errorMessage.value = ''
  try {
    await savePersonaSettings(enabled.value, content.value)
    content.value = content.value.trim()
    hint.value = '已保存'
  } catch (e) {
    errorMessage.value = e instanceof Error ? e.message : '保存失败，再试一次'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="row">
    <div class="row-text">
      <span class="row-label">自定义人格</span>
      <p class="f-hint">
        写一段话，定义它说话的样子；留空就用它自带的样子。改完保存，之后的消息就按你写的来。
      </p>
    </div>
    <ToggleSwitch v-model="enabled" label="自定义人格" />
  </div>
  <template v-if="enabled">
    <div class="field">
      <label for="f-soul">它是什么样的人</label>
      <textarea
        id="f-soul"
        v-model="content"
        class="soul-input"
        rows="8"
        :placeholder="loading ? '读取中…' : '例：你是一个话不多的朋友，说话很短，偶尔毒舌，但从不说教。'"
      />
      <p class="f-hint" :class="{ over: overLimit }">
        {{ usedLength }} / {{ maxLength }} 字
      </p>
    </div>
    <div class="d-btns soul-actions">
      <button class="link-btn" type="button" @click="showDefault = !showDefault">
        {{ showDefault ? '收起默认人格' : '查看默认人格' }}
      </button>
      <button class="btn-save" :disabled="saving || overLimit" @click="save">
        {{ saving ? '保存中…' : '保存' }}
      </button>
    </div>
    <div v-if="showDefault" class="default-box">
      <p class="d-note">它自带的样子（只读）：</p>
      <pre class="default-text">{{ defaultPersona }}</pre>
    </div>
  </template>
  <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>
  <p v-else-if="hint" class="d-note">{{ hint }}</p>
</template>

<style scoped>
.row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}
.row-text {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.row-label {
  font-size: var(--fs-helper);
  font-weight: 500;
  letter-spacing: 1px;
  color: var(--ink-2);
}
.soul-input {
  min-height: 140px;
  border: 1px solid var(--hairline-strong);
  border-radius: var(--radius);
  background: transparent;
  padding: 10px 12px;
  font-family: var(--sans);
  font-size: var(--fs-helper);
  line-height: 1.8;
  color: var(--ink-1);
  outline: none;
  resize: vertical;
  transition: border-color 260ms cubic-bezier(0.16, 1, 0.3, 1);
}
.soul-input:focus {
  border-color: var(--accent);
}
.f-hint.over {
  color: var(--accent);
}
.soul-actions {
  align-items: center;
  justify-content: space-between;
}
.link-btn {
  font-size: var(--fs-helper);
  color: var(--ink-2);
  text-decoration: underline;
  text-underline-offset: 3px;
}
.link-btn:hover {
  color: var(--accent);
}
.default-box {
  display: flex;
  flex-direction: column;
  gap: 8px;
  border: 1px solid var(--hairline);
  border-radius: 2px;
  padding: 10px 12px;
}
.default-text {
  margin: 0;
  max-height: 180px;
  overflow-y: auto;
  font-family: var(--sans);
  font-size: var(--fs-caption);
  line-height: 1.8;
  color: var(--ink-2);
  white-space: pre-wrap;
}
</style>
