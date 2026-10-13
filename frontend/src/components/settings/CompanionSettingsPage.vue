<script setup lang="ts">
// 设置 · 陪伴页：开关（默认关闭）+ 档位三选一；用户改动即保存。
// 关闭时与现状完全一致——你开口，它才回话；具体频率与时机由 05 的主动陪伴引擎执行。
//
// 不用 watch 监听保存：watch 会把 onMounted 的回填也当成一次"用户改动"（页面一打开就偷偷
// 写一遍），读取失败时还会把默认值写回去覆盖已存档位——改为显式在改动事件里保存（自审发现）。
import { onMounted, ref } from 'vue'

import { fetchCompanionSettings, saveCompanionSettings } from '../../api'
import SelectMenu, { type SelectOption } from '../shell/SelectMenu.vue'
import ToggleSwitch from '../shell/ToggleSwitch.vue'

const TIER_OPTIONS: SelectOption[] = [
  { value: 'cold', label: '冷淡（偶尔来看看）' },
  { value: 'normal', label: '正常' },
  { value: 'caring', label: '关心（来得勤一点）' },
]

const enabled = ref(false)
const tier = ref('normal')
const diaryReplyEnabled = ref(true) // 日记回应独立开关（v0.3.0 01），默认开启
const hint = ref('')
const errorMessage = ref('')

onMounted(async () => {
  try {
    const settings = await fetchCompanionSettings()
    enabled.value = settings.enabled
    tier.value = settings.tier
    diaryReplyEnabled.value = settings.diaryReplyEnabled
  } catch {
    errorMessage.value = '读取陪伴设置失败'
  }
})

async function persist(): Promise<void> {
  hint.value = ''
  errorMessage.value = ''
  try {
    await saveCompanionSettings(enabled.value, tier.value, diaryReplyEnabled.value)
    hint.value = '已保存'
  } catch (e) {
    errorMessage.value = e instanceof Error ? e.message : '保存失败'
  }
}

function onToggle(value: boolean): void {
  enabled.value = value
  void persist()
}

function onTier(value: string): void {
  tier.value = value
  void persist()
}

function onReplyToggle(value: boolean): void {
  diaryReplyEnabled.value = value
  void persist()
}
</script>

<template>
  <div class="row">
    <div class="row-text">
      <span class="row-label">主动陪伴</span>
      <p class="f-hint">
        开启后，它会在一天里自己找时机开口，像朋友一样；关闭时和现在完全一样——你开口，它才回话。
      </p>
    </div>
    <ToggleSwitch :model-value="enabled" label="主动陪伴" @update:model-value="onToggle" />
  </div>
  <div v-if="enabled" class="field">
    <label for="f-tier">档位</label>
    <SelectMenu
      id="f-tier"
      :model-value="tier"
      :options="TIER_OPTIONS"
      label="档位"
      @update:model-value="onTier"
    />
    <p class="f-hint">
      档位决定它开口的频率与姿态。无论哪一档，深夜都不会打扰；你不回，它也不会追着说。
    </p>
  </div>
  <div class="row">
    <div class="row-text">
      <span class="row-label">日记回应</span>
      <p class="f-hint">
        写完一条日记，它会在下面留一两句话。关闭后新日记不再生成回应，已经留下的还在。
      </p>
    </div>
    <ToggleSwitch
      :model-value="diaryReplyEnabled"
      label="日记回应"
      @update:model-value="onReplyToggle"
    />
  </div>
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
</style>
