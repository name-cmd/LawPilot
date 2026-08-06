<script setup lang="ts">
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'

/**
 * Markdown 渲染器 —— 全项目唯一允许 v-html 的组件。
 * 安全双保险：
 *   1. markdown-it 关闭 html 标签解析（html: false）
 *   2. 产物再过一遍 DOMPurify 消毒（过滤危险标签/属性）
 * 这是 XSS 的最后一道闸门，其他组件一律用 Vue 模板插值（自动转义）。
 */
const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

const props = defineProps<{ content: string }>()

const html = computed(() => DOMPurify.sanitize(md.render(props.content || '')))
</script>

<template>
  <div class="markdown-body" v-html="html" />
</template>

<style scoped>
/* Markdown 排版样式（法务文档风：紧凑、层次清晰） */
.markdown-body :deep(p) {
  margin: 0.5em 0;
  line-height: 1.75;
}
.markdown-body :deep(p:first-child) {
  margin-top: 0;
}
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  margin: 0.9em 0 0.4em;
  font-weight: 600;
  line-height: 1.4;
}
.markdown-body :deep(h1) {
  font-size: 1.15em;
}
.markdown-body :deep(h2) {
  font-size: 1.05em;
}
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  font-size: 1em;
}
.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 0.5em 0;
  padding-left: 1.4em;
}
.markdown-body :deep(li) {
  margin: 0.25em 0;
  line-height: 1.7;
}
.markdown-body :deep(strong) {
  font-weight: 600;
}
.markdown-body :deep(blockquote) {
  margin: 0.6em 0;
  padding: 0.4em 0.9em;
  border-left: 3px solid var(--color-brand-500);
  background: var(--color-surface-soft);
  border-radius: 0 8px 8px 0;
}
.markdown-body :deep(code) {
  font-family: Consolas, Monaco, monospace;
  font-size: 0.9em;
  background: var(--color-surface-soft);
  padding: 0.1em 0.4em;
  border-radius: 4px;
}
.markdown-body :deep(table) {
  border-collapse: collapse;
  margin: 0.6em 0;
  width: 100%;
  font-size: 0.92em;
}
.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid var(--color-line);
  padding: 0.4em 0.7em;
  text-align: left;
}
.markdown-body :deep(th) {
  background: var(--color-surface-soft);
  font-weight: 600;
}
</style>
