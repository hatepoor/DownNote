<script setup lang="ts">
// 条目回应卡（v0.3.0 01）：它对这篇日记的一两句留言 + 「聊聊 →」跳会话。
// 回应是条目附属物，不进会话、不弹通知；「聊聊」把原文转移进最近活跃会话。
import type { ReplyItem } from '../../api'

defineProps<{ reply: ReplyItem }>()
const emit = defineEmits<{ chat: [] }>()
</script>

<template>
  <div class="reply-card">
    <p class="reply-text">它：{{ reply.replyText }}</p>
    <button class="m-link reply-chat" @click="emit('chat')">聊聊 →</button>
  </div>
</template>

<style scoped>
.reply-card {
  margin-top: 8px;
  padding: 10px 12px;
  border-left: 2px solid var(--accent, #c89b6d);
  background: var(--bg-soft, rgba(0, 0, 0, 0.03));
  border-radius: 6px;
}
.reply-text {
  margin: 0;
  font-size: var(--fs-helper);
  color: var(--ink-2);
}
.reply-chat {
  float: right;
}
</style>
