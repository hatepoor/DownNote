<script setup lang="ts">
// 降级横幅：未配置模型时全局常驻，配置恢复后消失（产品不变量：记录永不失能）。
import { degraded } from '../stores/appState'

const emit = defineEmits<{ openSettings: [] }>()
</script>

<template>
  <div v-if="degraded" class="degraded-banner">
    <span class="db-text">未配置模型，仅可记录。日记不受影响，分析和唤醒对话会在配置后恢复。</span>
    <button class="btn-outline" @click="emit('openSettings')">配置模型</button>
  </div>
</template>
