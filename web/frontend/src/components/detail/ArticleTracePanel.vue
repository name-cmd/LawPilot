<script setup lang="ts">
import { ref } from 'vue'
import type { RetrievedArticle } from '@/api/types'

/**
 * 法条溯源面板：回答引用的法条卡片。
 * 废止标签：status 非 effective 显示「已废止 · 参见 xx」，否则显示「现行有效」。
 */
const props = defineProps<{ articles: RetrievedArticle[] }>()

// 展开全文：记录已展开的卡片下标
const expanded = ref<Set<number>>(new Set())

function validityTag(a: RetrievedArticle) {
  const status = a.status || 'effective'
  if (status !== 'effective') {
    return { text: a.superseded_by ? `已废止 · 参见${a.superseded_by}` : '已废止', cls: 'bg-danger/10 text-danger' }
  }
  return a.effective_date ? { text: '现行有效', cls: 'bg-success/10 text-success' } : null
}

function toggleExpand(i: number) {
  const next = new Set(expanded.value)
  if (next.has(i)) next.delete(i)
  else next.add(i)
  expanded.value = next
}
</script>

<template>
  <div v-if="!props.articles?.length" class="px-1 pt-10 text-center text-[12px] text-muted">
    无检索结果
  </div>

  <div v-else class="space-y-2">
    <div
      v-for="(a, i) in props.articles" :key="`${a.law_name}-${a.article_num}-${i}`"
      class="rounded-xl border border-line bg-surface p-3"
      :class="(a.status || 'effective') !== 'effective' ? 'border-danger/30' : ''"
    >
      <div class="text-[12px] font-semibold text-ink">
        《{{ a.law_name }}》{{ a.article_num }}
        <span
          v-if="validityTag(a)"
          class="ml-1 rounded px-1.5 py-0.5 text-[10px] font-normal"
          :class="validityTag(a)?.cls"
        >
          {{ validityTag(a)?.text }}
        </span>
      </div>

      <div v-if="a.relevance_score != null" class="mt-0.5 text-[11px] text-muted">
        相关度 {{ (a.relevance_score * 100).toFixed(0) }}%
      </div>

      <p class="mt-1.5 whitespace-pre-wrap text-[12px] leading-relaxed text-muted">
        {{ expanded.has(i) ? a.content : (a.content || '').slice(0, 280) + ((a.content || '').length > 280 ? '…' : '') }}
      </p>

      <button
        v-if="(a.content || '').length > 280"
        class="mt-1 text-[11px] text-brand-500 hover:underline"
        @click="toggleExpand(i)"
      >
        {{ expanded.has(i) ? '收起' : '展开全文' }}
      </button>
    </div>
  </div>
</template>
