<script setup lang="ts">
// 模型配置弹窗（03-模型接口 / 12-体验修订）：五字段保存即生效。
// API Key 掩码回显、不回显明文；温度与思考强度带注释说明，真实作用于模型调用。
import { onMounted, ref } from 'vue'

import { fetchModelSettings, saveModelSettings } from '../../api'
import SelectMenu, { type SelectOption } from './SelectMenu.vue'

const REASONING_OPTIONS: SelectOption[] = [
  { value: '', label: '关闭（不传该参数）' },
  { value: 'low', label: '低' },
  { value: 'medium', label: '中' },
  { value: 'high', label: '高' },
]

const emit = defineEmits<{ close: []; saved: [] }>()

const baseUrl = ref('')
const modelName = ref('')
const apiKey = ref('')
const apiKeyMasked = ref('')
const temperature = ref(1.1)
const reasoningEffort = ref('low')
const saving = ref(false)
const errorMessage = ref('')

onMounted(async () => {
  try {
    const settings = await fetchModelSettings()
    baseUrl.value = settings.baseUrl
    modelName.value = settings.modelName
    apiKeyMasked.value = settings.apiKeyMasked
    temperature.value = settings.temperature
    reasoningEffort.value = settings.reasoningEffort
  } catch {
    // 读取失败保持空表单，保存时仍会给出错误提示
  }
})

async function save(): Promise<void> {
  if (!baseUrl.value.trim() || !modelName.value.trim()) {
    errorMessage.value = 'Base URL 与模型名不能为空'
    return
  }
  if (Number.isNaN(temperature.value) || temperature.value < 0 || temperature.value > 2) {
    errorMessage.value = '温度需要在 0 到 2 之间'
    return
  }
  saving.value = true
  errorMessage.value = ''
  try {
    await saveModelSettings(
      baseUrl.value.trim(),
      modelName.value.trim(),
      apiKey.value,
      temperature.value,
      reasoningEffort.value,
    )
    emit('saved')
    emit('close')
  } catch (e) {
    errorMessage.value = e instanceof Error ? e.message : '保存失败，再试一次'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="dialog-scrim" @click.self="emit('close')">
    <div class="dialog" role="dialog" aria-label="配置模型">
      <h2>配置模型</h2>
      <div class="field">
        <label for="f-url">Base URL</label>
        <input id="f-url" v-model="baseUrl" placeholder="https://api.example.com/v1" />
        <p class="f-hint">
          仅支持 OpenAI 兼容的 completions 模式（自动请求 /chat/completions），填到 /v1 一层即可。
        </p>
      </div>
      <div class="field">
        <label for="f-key">API Key</label>
        <input id="f-key" v-model="apiKey" type="password" :placeholder="apiKeyMasked || 'sk-…'" />
      </div>
      <div class="field">
        <label for="f-model">模型名</label>
        <input id="f-model" v-model="modelName" placeholder="如 gpt-4o-mini" />
      </div>
      <div class="field">
        <label for="f-temp">温度</label>
        <input id="f-temp" v-model.number="temperature" type="number" step="0.1" min="0" max="2" />
        <p class="f-hint">数值越大回答越发散、越有变化；越小越固定、越保守（0–2）。</p>
      </div>
      <div class="field">
        <label for="f-reasoning">思考强度</label>
        <SelectMenu id="f-reasoning" v-model="reasoningEffort" :options="REASONING_OPTIONS" label="思考强度" />
        <p class="f-hint">
          推理型模型的思考量。关闭则不向模型传该参数；部分模型内部仍会思考，无法强制关停。
        </p>
      </div>
      <p class="d-note">配置只保存在这台电脑上。</p>
      <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>
      <div class="d-btns">
        <button class="btn-cancel" @click="emit('close')">取消</button>
        <button class="btn-save" :disabled="saving" @click="save">
          {{ saving ? '保存中…' : '保存' }}
        </button>
      </div>
    </div>
  </div>
</template>
