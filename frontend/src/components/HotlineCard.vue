<script setup lang="ts">
// 求助资源卡：暖纸卡、电话一键复制，"朋友递纸条"姿态（ADR-0003、front_design/04）。
import { ref } from 'vue'

import type { Hotline } from '../api/client'

defineProps<{ hotlines: Hotline[] }>()

const copiedIndex = ref<number | null>(null)

async function copy(phone: string, index: number): Promise<void> {
  await navigator.clipboard.writeText(phone)
  copiedIndex.value = index
  window.setTimeout(() => (copiedIndex.value = null), 1500)
}
</script>

<template>
  <div class="hotline-card">
    <p class="title">一些可以打给你的声音</p>
    <div v-for="(h, i) in hotlines" :key="h.phone + String(i)" class="hotline">
      <span class="name">{{ h.name }}<span class="region">{{ h.region }}</span></span>
      <span class="phone">{{ h.phone }}</span>
      <button class="copy" @click="copy(h.phone, i)">{{ copiedIndex === i ? '已复制' : '复制' }}</button>
    </div>
    <p class="tail">不评判，随时都在。</p>
  </div>
</template>
