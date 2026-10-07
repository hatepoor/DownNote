// 滚动边缘渐进渐出：给滚动容器注入 .scroll-fade 并驱动 --fade-top/--fade-bottom。
// 渐隐范围随滚动位置连续变化（到顶/到底时该侧为 0）——不是遮罩叠加，无"突现"感。
import { onBeforeUnmount, watch, type Ref } from 'vue'

const FADE_PX = 22

export function useScrollFade(elRef: Ref<HTMLElement | null>): void {
  let el: HTMLElement | null = null
  let mutation: MutationObserver | null = null
  let resize: ResizeObserver | null = null

  function update(): void {
    if (!el) return
    const top = Math.max(0, Math.min(FADE_PX, el.scrollTop))
    const rest = el.scrollHeight - el.clientHeight - el.scrollTop
    const bottom = Math.max(0, Math.min(FADE_PX, rest))
    el.style.setProperty('--fade-top', `${top}px`)
    el.style.setProperty('--fade-bottom', `${bottom}px`)
  }

  function attach(target: HTMLElement): void {
    el = target
    el.classList.add('scroll-fade')
    update()
    el.addEventListener('scroll', update, { passive: true })
    // 内容增删、文字变化（如流式）与容器尺寸变化都要重算渐隐范围
    mutation = new MutationObserver(update)
    mutation.observe(el, { childList: true, subtree: true, characterData: true })
    resize = new ResizeObserver(update)
    resize.observe(el)
  }

  function detach(): void {
    el?.removeEventListener('scroll', update)
    mutation?.disconnect()
    resize?.disconnect()
    mutation = null
    resize = null
    el = null
  }

  // ref 随 v-if 分支挂载/卸载，watch 跟着接上与摘掉
  watch(elRef, (target) => {
    detach()
    if (target) attach(target)
  }, { flush: 'post', immediate: true })

  onBeforeUnmount(detach)
}
