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

/**
 * 法条条号/法律名称高亮（highlightArticle 时启用）：markdown-it 的 text 规则会把
 * 整段普通文本一次性收集，自定义 inline 插件规则永远无法命中「第三十一条」「《劳动法》」
 * （已实测复现），因此改为渲染后文本替换：先包法律名称（书名号内整段），再包条号
 * （阿拉伯/中文数字），各自包上 <span class="law-name"> / <span class="article-no">，
 * 再走 DOMPurify 消毒（span + class 属性在白名单内）。可命中加粗、列表等任意位置。
 */
const ARTICLE_NO_RE = /第[0-9一二三四五六七八九十百千零两]+条/g
const LAW_NAME_RE = /《[^《》]+》/g

const props = defineProps<{ content: string; highlightArticle?: boolean }>()

const html = computed(() => {
  let out = md.render(props.content || '')
  if (props.highlightArticle) {
    // 顺序：先法律名称（书名号内），再条号 —— 二者互不重叠（书名号内不含「第X条」）
    out = out.replace(LAW_NAME_RE, (m) => `<span class="law-name">${m}</span>`)
    out = out.replace(ARTICLE_NO_RE, (m) => `<span class="article-no">${m}</span>`)
  }
  return DOMPurify.sanitize(out)
})
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
/* 法律名称高亮（如《劳动法》）：与条号同款品牌蓝加粗，另加斜体作视觉区分
   （书名号 + 斜体符合中文法律文书排版惯例）；nowrap 防止在行尾被拆成两行 */
.markdown-body :deep(.law-name) {
  color: var(--color-brand-500);
  font-weight: 600;
  font-style: italic;
  white-space: nowrap;
}
/* 法条条号高亮：品牌蓝加粗（highlightArticle 时输出），与正文黑色区分；
   nowrap 防止「第三十一条」在行尾被拆成两行 */
.markdown-body :deep(.article-no) {
  color: var(--color-brand-500);
  font-weight: 600;
  white-space: nowrap;
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
