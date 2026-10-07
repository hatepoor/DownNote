<script setup lang="ts">
// 自绘标题栏（仅 Tauri 壳渲染）：拖拽区 + 窗口控制钮，随应用主题走；浏览器/开发态由系统接管
import { getCurrentWindow } from '@tauri-apps/api/window'

const appWindow = getCurrentWindow()
</script>

<template>
  <header class="titlebar" data-tauri-drag-region>
    <div class="t-brand" data-tauri-drag-region>
      <span class="t-seal">低</span>
      <span class="t-name">低落日记</span>
    </div>
    <div class="t-controls">
      <button class="t-btn" aria-label="最小化" @click="appWindow.minimize()">
        <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">
          <path d="M2 6h8" stroke="currentColor" stroke-width="1" />
        </svg>
      </button>
      <button class="t-btn" aria-label="最大化" @click="appWindow.toggleMaximize()">
        <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">
          <rect x="2.5" y="2.5" width="7" height="7" fill="none" stroke="currentColor" stroke-width="1" />
        </svg>
      </button>
      <button class="t-btn t-close" aria-label="关闭" @click="appWindow.close()">
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
  gap: 8px;
}
.t-seal {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent);
  color: var(--on-accent);
  font-family: var(--serif);
  font-size: 12px;
  border-radius: 2px;
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
