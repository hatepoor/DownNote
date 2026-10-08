<script lang="ts">
// 对外类型：选项由父组件传入，value 与 v-model 对齐
export interface SelectOption {
  value: string
  label: string
}
</script>

<script setup lang="ts">
// 自绘下拉（SelectMenu）：替代原生 <select> 的弹出层。
// 浏览器picker（base-select）在不同内核下有错位、收起重影等怪癖，且样式不可靠接管；
// 改为页内绝对定位渲染：触发框下方全宽展开，视觉与动效全部走设计 token。
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps<{
  modelValue: string
  options: SelectOption[]
  /** 触发按钮的无障碍名称（一般与字段 label 同文） */
  label?: string
  /** 关联字段 label 的 for 属性 */
  id?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const rootEl = ref<HTMLElement | null>(null)
const triggerEl = ref<HTMLButtonElement | null>(null)
const listEl = ref<HTMLUListElement | null>(null)
const open = ref(false)
const activeIndex = ref(-1)

const listId = `select-menu-${Math.random().toString(36).slice(2, 8)}`
const activeId = computed(() =>
  activeIndex.value >= 0 ? `${listId}-opt-${activeIndex.value}` : undefined,
)

const selectedLabel = computed(
  () => props.options.find((op) => op.value === props.modelValue)?.label ?? '',
)

function openMenu(): void {
  if (open.value) return
  open.value = true
  activeIndex.value = Math.max(
    0,
    props.options.findIndex((op) => op.value === props.modelValue),
  )
}

function close(refocusTrigger = true): void {
  if (!open.value) return
  open.value = false
  activeIndex.value = -1
  if (refocusTrigger) triggerEl.value?.focus()
}

function choose(option: SelectOption): void {
  emit('update:modelValue', option.value)
  close()
}

function toggle(): void {
  if (open.value) close()
  else openMenu()
}

function onTriggerKeydown(event: KeyboardEvent): void {
  // Enter/Space 交给 <button> 的原生激活（走 click → toggle）；
  // 这里若也处理会"keydown 开、原生 click 关"，菜单开完即关
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    openMenu()
  }
}

function onListKeydown(event: KeyboardEvent): void {
  const count = props.options.length
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    const delta = event.key === 'ArrowDown' ? 1 : -1
    activeIndex.value = (activeIndex.value + delta + count) % count
  } else if (event.key === 'Home') {
    event.preventDefault()
    activeIndex.value = 0
  } else if (event.key === 'End') {
    event.preventDefault()
    activeIndex.value = count - 1
  } else if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    const option = props.options[activeIndex.value]
    if (option) choose(option)
  } else if (event.key === 'Escape') {
    event.preventDefault()
    close()
  } else if (event.key === 'Tab') {
    close(false)
  }
}

function onDocPointerDown(event: PointerEvent): void {
  if (rootEl.value && !rootEl.value.contains(event.target as Node)) close(false)
}

watch(open, (isOpen) => {
  if (isOpen) {
    document.addEventListener('pointerdown', onDocPointerDown)
    nextTick(() => listEl.value?.focus())
  } else {
    document.removeEventListener('pointerdown', onDocPointerDown)
  }
})

onBeforeUnmount(() => document.removeEventListener('pointerdown', onDocPointerDown))
</script>

<template>
  <div ref="rootEl" class="select">
    <button
      :id="id"
      ref="triggerEl"
      type="button"
      class="select-trigger"
      role="combobox"
      aria-haspopup="listbox"
      :aria-expanded="open"
      :aria-controls="open ? listId : undefined"
      :aria-label="label"
      @click="toggle"
      @keydown="onTriggerKeydown"
    >
      <span class="select-value">{{ selectedLabel }}</span>
      <span class="select-arrow" aria-hidden="true"></span>
    </button>
    <Transition name="ink">
      <ul
        v-if="open"
        :id="listId"
        ref="listEl"
        class="select-list"
        role="listbox"
        :aria-label="label"
        :aria-activedescendant="activeId"
        tabindex="-1"
        @keydown="onListKeydown"
      >
        <li
          v-for="(option, index) in options"
          :id="`${listId}-opt-${index}`"
          :key="option.value"
          class="select-option"
          role="option"
          :class="{ active: index === activeIndex, checked: option.value === modelValue }"
          :aria-selected="option.value === modelValue"
          @pointerenter="activeIndex = index"
          @click="choose(option)"
        >
          {{ option.label }}
        </li>
      </ul>
    </Transition>
  </div>
</template>

<style scoped>
.select {
  position: relative;
}
.select-trigger {
  width: 100%;
  height: 38px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  border: 1px solid var(--hairline-strong);
  border-radius: var(--radius);
  background: transparent;
  padding: 0 12px;
  font-family: var(--sans);
  font-size: var(--fs-helper);
  color: var(--ink-1);
  text-align: left;
  transition: border-color 260ms cubic-bezier(0.16, 1, 0.3, 1);
}
.select-trigger:focus {
  outline: none;
}
.select-trigger:focus-visible {
  outline: 2px solid var(--focus-ring);
  outline-offset: 2px;
}
/* 展开时与弹出层同为朱砂描边（延续原生下拉的视觉语言） */
.select-trigger[aria-expanded='true'] {
  border-color: var(--accent);
}
.select-arrow {
  width: 0;
  height: 0;
  border-left: 4px solid transparent;
  border-right: 4px solid transparent;
  border-top: 5px solid var(--ink-2);
}
.select-list {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  z-index: 5;
  margin: 0;
  padding: 4px 0;
  list-style: none;
  background: var(--bg-sheet);
  border: 1px solid var(--accent);
  border-radius: var(--radius-overlay);
  box-shadow: 0 16px 48px -8px var(--shadow-dialog);
  max-height: 280px;
  overflow-y: auto;
  outline: none;
}
.select-option {
  padding: 8px 12px;
  font-size: var(--fs-helper);
  color: var(--ink-1);
  cursor: pointer;
  transition:
    background-color 180ms ease,
    color 180ms ease;
}
.select-option.active,
.select-option.checked {
  background: var(--accent-soft);
}
.select-option.checked {
  color: var(--accent);
  font-weight: 500;
}
</style>
