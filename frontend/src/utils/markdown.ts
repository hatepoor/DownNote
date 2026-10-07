// Markdown 渲染：模型回复 → 安全 HTML（marked 解析 + DOMPurify 消毒）。
// 12-体验修订：Agent 可用少量 Markdown，前端负责渲染成信笺铅字风格的富文本。
import DOMPurify from 'dompurify'
import { marked } from 'marked'

marked.setOptions({ breaks: true, gfm: true })

export function renderMarkdown(text: string): string {
  const html = marked.parse(text, { async: false }) as string
  return DOMPurify.sanitize(html)
}
