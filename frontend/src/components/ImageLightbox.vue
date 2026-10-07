<script setup lang="ts">
// 图片查看：遮罩 + 原图居中，点击任意处关闭（front_design/03 §5）
import { onMounted, onUnmounted } from 'vue'

defineProps<{ url: string }>()

const emit = defineEmits<{ close: [] }>()

function onKeydown(e: KeyboardEvent): void {
  if (e.key === 'Escape') emit('close')
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div class="lightbox" @click="emit('close')">
    <img :src="url" alt="日记配图原图" />
  </div>
</template>
