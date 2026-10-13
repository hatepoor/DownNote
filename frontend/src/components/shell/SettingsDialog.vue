<script setup lang="ts">
// 设置弹窗（v0.2.0 02）：侧边栏三页——模型 / 陪伴 / 人格。
// 页面各自承担动作：模型页与人格页手动保存，陪伴页改动即时保存；弹窗底部只留「关闭」。
import { ref } from 'vue'

import CompanionSettingsPage from '../settings/CompanionSettingsPage.vue'
import ModelSettingsPage from '../settings/ModelSettingsPage.vue'
import PersonaSettingsPage from '../settings/PersonaSettingsPage.vue'

const emit = defineEmits<{ close: []; saved: [] }>()

type SettingsPage = 'model' | 'companion' | 'persona'

const PAGES: { id: SettingsPage; label: string }[] = [
  { id: 'model', label: '模型' },
  { id: 'companion', label: '陪伴' },
  { id: 'persona', label: '人格' },
]

const page = ref<SettingsPage>('model')
</script>

<template>
  <div class="dialog-scrim" @click.self="emit('close')">
    <div class="dialog settings-dialog" role="dialog" aria-label="设置">
      <h2>设置</h2>
      <div class="s-body">
        <nav class="s-nav" aria-label="设置分区">
          <button
            v-for="item in PAGES"
            :key="item.id"
            type="button"
            class="s-nav-item"
            :class="{ active: page === item.id }"
            :aria-current="page === item.id ? 'true' : undefined"
            @click="page = item.id"
          >
            {{ item.label }}
          </button>
        </nav>
        <div class="s-page">
          <ModelSettingsPage v-if="page === 'model'" @saved="emit('saved')" />
          <CompanionSettingsPage v-else-if="page === 'companion'" />
          <PersonaSettingsPage v-else />
        </div>
      </div>
      <div class="d-btns">
        <button class="btn-cancel" @click="emit('close')">关闭</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.settings-dialog {
  width: 640px;
}
.s-body {
  display: flex;
  gap: 20px;
  min-height: 330px;
}
.s-nav {
  display: flex;
  flex: none;
  flex-direction: column;
  gap: 2px;
  width: 92px;
  padding-right: 12px;
  border-right: 1px solid var(--hairline);
}
.s-nav-item {
  text-align: left;
  padding: 8px 12px;
  border-radius: 2px;
  font-size: var(--fs-helper);
  letter-spacing: 1px;
  color: var(--ink-2);
}
.s-nav-item:hover,
.s-nav-item.active {
  color: var(--accent);
  background: var(--accent-soft);
}
.s-page {
  display: flex;
  flex: 1;
  min-width: 0;
  flex-direction: column;
  gap: 16px;
}
</style>
