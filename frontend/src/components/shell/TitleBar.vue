<script setup lang="ts">
// 应用自绘标题栏：Tauri 壳与开发态无边框窗口都渲染（浏览器里由浏览器自己接管）。
// 窗口动作经 appState.windowAction 分发，两条壳的按钮语义一致。
import { windowAction } from '../../stores/appState'
</script>

<template>
  <header class="titlebar pywebview-drag-region" data-tauri-drag-region>
    <div class="t-brand pywebview-drag-region" data-tauri-drag-region>
      <span class="t-name pywebview-drag-region">低落日记</span>
    </div>
    <div class="t-controls">
      <button class="t-btn" aria-label="最小化" @click="windowAction('minimize')">
        <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">
          <path d="M2 6h8" stroke="currentColor" stroke-width="1" />
        </svg>
      </button>
      <button class="t-btn" aria-label="最大化" @click="windowAction('toggleMaximize')">
        <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">
          <rect x="2.5" y="2.5" width="7" height="7" fill="none" stroke="currentColor" stroke-width="1" />
        </svg>
      </button>
      <button class="t-btn t-close" aria-label="关闭" @click="windowAction('close')">
        <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">
          <path d="M3 3l6 6M9 3l-6 6" stroke="currentColor" stroke-width="1" />
        </svg>
      </button>
    </div>
  </header>
</template>

<style scoped>
.titlebar {
  height: 36px;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--bg-page);
  border-bottom: 1px solid var(--hairline);
  user-select: none;
  padding-left: 12px;
}
.t-brand {
  display: flex;
  align-items: center;
}
.t-name {
  font-family: var(--serif);
  font-size: var(--fs-helper);
  letter-spacing: 2px;
  color: var(--ink-2);
}
.t-controls {
  display: flex;
  height: 100%;
}
.t-btn {
  width: 46px;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--ink-2);
}
.t-btn:hover {
  background: var(--bg-inset);
  color: var(--ink-1);
}
.t-close:hover {
  background: #c42b1c;
  color: #fff;
}
</style>
