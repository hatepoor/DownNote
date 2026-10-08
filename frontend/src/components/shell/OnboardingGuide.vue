<script setup lang="ts">
// 首次启动引导（07-新手引导）：三步（写记录 → 配模型 → 唤醒对话），可跳过。
// 标记由 App 落盘（stores/onboarding.ts）；外观复用浮层骨架，只补步骤文案的排版。
import { ref } from 'vue'

const emit = defineEmits<{ done: []; openSettings: [] }>()

const STEPS = [
  {
    title: '先写一句',
    body: '左边这块信笺就是写日记的地方，几个字也行。写完会自动收好——只存在你这台电脑上，不上传。',
  },
  {
    title: '接上一个模型',
    body: '点侧栏的「设置」，填 Base URL、API Key 和模型名（填到 /v1 一层）。填好之后它才会读你写的东西、跟你说话；没填也能照常写日记。',
  },
  {
    title: '它在右边等你',
    body: '中间竖线右边是对话栏。想聊就点一下，它会先读完你最近写的东西，然后跟你搭话。',
  },
]

const step = ref(0)

function next(): void {
  if (step.value < STEPS.length - 1) {
    step.value += 1
    return
  }
  emit('done')
}
</script>

<template>
  <div class="dialog-scrim" @click.self="emit('done')">
    <div class="dialog" role="dialog" aria-label="新手引导">
      <p class="o-step">第 {{ step + 1 }} 步 / 共 {{ STEPS.length }} 步</p>
      <h2>{{ STEPS[step].title }}</h2>
      <p class="o-body">{{ STEPS[step].body }}</p>
      <div class="d-btns">
        <button class="btn-cancel" @click="emit('done')">跳过</button>
        <button v-if="step === 1" class="btn-cancel" @click="emit('openSettings'); emit('done')">
          去设置
        </button>
        <button class="btn-save" @click="next">
          {{ step === STEPS.length - 1 ? '开始写' : '下一步' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 复用浮层骨架（.dialog-scrim / .dialog / .d-btns 均为全局样式），只补步骤文案排版 */
.o-step {
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 2px;
  color: var(--ink-3);
  margin-bottom: 6px;
}
.o-body {
  font-size: var(--fs-helper);
  line-height: 1.9;
  color: var(--ink-1);
}
</style>
