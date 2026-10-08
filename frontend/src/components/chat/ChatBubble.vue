<script setup lang="ts">
// 消息气泡：Agent 靠左（2px 墨缘、宋体；Markdown 渲染）；用户靠右（朱砂洗底、纯文本）。
// streaming 时末尾显示朱砂光标（800ms 呼吸，样式挂在 .md-body.streaming 上）。
import { computed } from 'vue'

import { renderMarkdown } from '../../utils/markdown'

const props = defineProps<{ role: 'user' | 'assistant'; content: string; streaming?: boolean }>()

const renderedHtml = computed(() => (props.role === 'assistant' ? renderMarkdown(props.content) : ''))
</script>

<template>
  <div :class="role === 'user' ? 'msg-user' : 'msg-agent'">
    <p v-if="role === 'user'">{{ content }}</p>
    <div v-else class="md-body" :class="{ streaming }" v-html="renderedHtml" />
  </div>
</template>
