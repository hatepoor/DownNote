<script setup lang="ts">
// 开关（陪伴 / 人格页共用）：button + role="switch"，键盘可达；
// 轨道不用药丸形——按全局 2px 圆角纪律做方轨（视觉以 02 号规范为准）。
const model = defineModel<boolean>({ default: false })

defineProps<{ label: string; id?: string }>()
</script>

<template>
  <button
    :id="id"
    type="button"
    class="toggle"
    role="switch"
    :aria-checked="model"
    :aria-label="label"
    @click="model = !model"
  >
    <span class="track" aria-hidden="true"><span class="knob" /></span>
  </button>
</template>

<style scoped>
.toggle {
  padding: 0;
  border: none;
  background: transparent;
  line-height: 0;
}
.track {
  display: inline-block;
  position: relative;
  width: 38px;
  height: 20px;
  border: 1px solid var(--hairline-strong);
  border-radius: 2px;
  background: transparent;
  transition:
    background-color 200ms ease,
    border-color 200ms ease;
}
.knob {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 14px;
  height: 14px;
  border-radius: 2px;
  background: var(--ink-3);
  transition:
    transform 200ms cubic-bezier(0.16, 1, 0.3, 1),
    background-color 200ms ease;
}
.toggle[aria-checked='true'] .track {
  background: var(--accent-soft);
  border-color: var(--accent);
}
.toggle[aria-checked='true'] .knob {
  transform: translateX(18px);
  background: var(--accent-fill);
}
.toggle:focus-visible .track {
  outline: 2px solid var(--focus-ring);
  outline-offset: 2px;
}
</style>
