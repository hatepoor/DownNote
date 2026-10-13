<script setup lang="ts">
// 条目回应卡（v0.3.0 01）：它对这篇日记的一两句留言 + 「聊聊 →」跳会话。
// 形态：四角各一段起笔于角、沿边渐隐化开的角标线（--margin-line）——信纸页边的语言，
// 不用整条实色竖条（守 §4 朱砂纪律：朱砂只出现在主按钮/光标/唤醒入口/印章/焦虑标签）。
// 正文走宋体，与用户自己的正文拉开距离。
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
  position: relative;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  margin-top: 10px;
  padding: 9px 13px;
  border-radius: 2px; /* 全局圆角纪律 */
}
/* 四角包裹：每角两段短线（一横一竖），自角上最实、沿边渐隐化开 */
.reply-card::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background-repeat: no-repeat;
  background-image:
    linear-gradient(90deg, var(--margin-line) 0%, transparent 100%),
    linear-gradient(180deg, var(--margin-line) 0%, transparent 100%),
    linear-gradient(270deg, var(--margin-line) 0%, transparent 100%),
    linear-gradient(180deg, var(--margin-line) 0%, transparent 100%),
    linear-gradient(90deg, var(--margin-line) 0%, transparent 100%),
    linear-gradient(0deg, var(--margin-line) 0%, transparent 100%),
    linear-gradient(270deg, var(--margin-line) 0%, transparent 100%),
    linear-gradient(0deg, var(--margin-line) 0%, transparent 100%);
  background-size:
    22px 1px,
    1px 22px,
    22px 1px,
    1px 22px,
    22px 1px,
    1px 22px,
    22px 1px,
    1px 22px;
  background-position:
    left top,
    left top,
    right top,
    right top,
    left bottom,
    left bottom,
    right bottom,
    right bottom;
}
.reply-text {
  flex: 1;
  margin: 0;
  font-family: var(--serif);
  font-size: var(--fs-helper);
  line-height: 1.6;
  color: var(--ink-2);
}
.reply-chat {
  flex: none;
  white-space: nowrap;
}
</style>
