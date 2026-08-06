<script setup lang="ts">
import { computed } from 'vue'
import type { CitationVerification, ExtractedCitation } from '@/api/types'

/**
 * 引用核验面板：显式引用对比卡片 + 隐性论断 + 汇总。
 * 对比盒：左栏「模型论述摘录」vs 右栏「法条对照原文」。
 */
const props = defineProps<{
  pending: boolean
  verification: CitationVerification | null
  regenerationAttempts?: number
}>()

const citations = computed(() => props.verification?.extracted_citations || [])
const implicits = computed(() => props.verification?.implicit_claims || [])

function severityClass(c: ExtractedCitation) {
  if (c.severity === 'error') return 'border-danger/40'
  if (c.severity === 'warning') return 'border-warning/40'
  return 'border-line'
}

function verdictClass(v?: string) {
  if (!v) return 'text-danger'
  if (v.includes('✅') || v.includes('准确')) return 'text-success'
  if (v.includes('⚠')) return 'text-warning'
  return 'text-danger'
}
</script>

<template>
  <!-- 核验中 -->
  <div v-if="pending" class="px-1 pt-10 text-center">
    <p class="text-[13px] text-warning">引用核验中…</p>
    <p class="mt-1 text-[11px] text-muted">正在比对模型引用与知识库原文</p>
  </div>

  <!-- 无数据 -->
  <div
    v-else-if="!citations.length && !implicits.length"
    class="px-1 pt-10 text-center text-[12px] text-muted"
  >
    无显式引用或未检测
  </div>

  <div v-else class="space-y-2">
    <!-- 显式引用卡片 -->
    <div
      v-for="(c, i) in citations" :key="i"
      class="rounded-xl border bg-surface p-3"
      :class="severityClass(c)"
    >
      <div class="text-[12px] font-medium text-ink">{{ c.text }}</div>

      <!-- 裁决 -->
      <div class="mt-1 text-[11px] font-semibold" :class="verdictClass(c.verdict)">
        {{ c.verdict || '' }}
      </div>

      <!-- 废止警告 -->
      <div v-if="c.validity && !c.validity.effective" class="mt-1 text-[11px] text-danger">
        {{ c.validity.warning_message || '已废止' }}
      </div>

      <!-- 吻合度 -->
      <div v-if="c.content_match_score != null" class="mt-1 text-[11px] text-muted">
        吻合度：{{ (c.content_match_score * 100).toFixed(0) }}%
      </div>

      <!-- 是否在检索结果内 -->
      <div class="mt-0.5 text-[10px] text-muted">
        {{ c.in_retrieved_context === true ? '✓ 在本次检索结果内' : c.in_retrieved_context === false ? '✗ 不在本次检索结果内' : '' }}
      </div>

      <!-- 对比盒：模型论述 vs 法条原文 -->
      <div
        v-if="c.quoted_text || c.reference_excerpt || c.actual_content"
        class="mt-2 grid grid-cols-2 gap-2"
      >
        <div class="rounded-lg bg-page p-2">
          <div class="mb-1 text-[10px] font-semibold text-muted">模型论述摘录</div>
          <p class="text-[11px] leading-relaxed text-ink">
            {{ c.quoted_text || c.arguing_sentence || '（未摘录）' }}
          </p>
        </div>
        <div class="rounded-lg bg-page p-2">
          <div class="mb-1 text-[10px] font-semibold text-muted">法条对照原文</div>
          <p class="text-[11px] leading-relaxed text-ink">
            {{ (c.reference_excerpt || c.actual_content || '').slice(0, 400) }}
          </p>
        </div>
      </div>
    </div>

    <!-- 隐性论断 -->
    <template v-if="implicits.length">
      <div class="pt-1 text-[12px] font-semibold text-ink">隐性法律论断核验</div>
      <div
        v-for="(im, i) in implicits" :key="i"
        class="rounded-xl border border-line bg-surface p-3"
      >
        <div class="text-[12px] text-ink">{{ im.claim || im.text || '' }}</div>
        <div
          class="mt-1 text-[11px] font-semibold"
          :class="im.supported ? 'text-success' : 'text-warning'"
        >
          {{ im.supported ? '✓ 有法律支撑' : '⚠ 支撑不足' }}
          （{{ ((im.support_score || 0) * 100).toFixed(0) }}%）
        </div>
      </div>
    </template>

    <!-- 汇总说明 -->
    <pre
      v-if="verification?.summary"
      class="mt-1 whitespace-pre-wrap rounded-lg bg-page px-3 py-2 text-[11px] leading-relaxed text-muted"
    >{{ verification.summary }}</pre>

    <!-- 自动修正提示 -->
    <div
      v-if="regenerationAttempts"
      class="rounded-lg bg-warning/10 px-2.5 py-1.5 text-[11px] text-warning"
    >
      已自动修正引用 {{ regenerationAttempts }} 次
    </div>
  </div>
</template>
