<script setup lang="ts">
import { computed } from 'vue'
import type { MessageMeta } from '@/api/types'
import { isLegalAnalysisMeta, isVerificationPending } from '@/utils/answer'

/**
 * 可信分徽章（AI 回复卡片头部右侧）：
 * - 核验中：灰色徽章提示待核验 / 快速评分
 * - 核验完成：金/绿渐变徽章「★ 综合可信分 85.8 - 高可信」
 * - 附带废止法条警告
 */
const props = defineProps<{ meta?: MessageMeta }>()

const legal = computed(() => isLegalAnalysisMeta(props.meta))
const pending = computed(() => isVerificationPending(props.meta))
const score = computed(() => props.meta?.trust?.overall_score ?? null)

const hasValidityWarnings = computed(() => Boolean(props.meta?.validity_warnings?.length))
</script>

<template>
  <div v-if="legal" class="flex items-center gap-2">
    <!-- 核验中 / 快速评分（灰底，动态呼吸点） -->
    <span
      v-if="pending"
      class="inline-flex items-center gap-1 rounded-full bg-slate-200 px-2.5 py-1 text-[11px] font-medium text-slate-600 dark:bg-slate-700 dark:text-slate-300"
    >
      <span class="h-1.5 w-1.5 animate-breathe rounded-full bg-slate-400" />
      {{ score === null ? '引用核验中…' : `可信分 ${score}（核验中…）` }}
    </span>

    <!-- 核验完成：金/绿渐变徽章 -->
    <span
      v-else-if="score !== null"
      class="inline-flex items-center gap-1 rounded-full bg-gradient-to-r from-amber-400 to-green-500 px-2.5 py-1 text-[11px] font-medium text-white shadow-sm"
    >
      ★ 综合可信分 {{ score }}
      <span v-if="props.meta?.trust?.trust_level" class="font-normal opacity-90">
        - {{ props.meta.trust.trust_level }}
      </span>
    </span>

    <!-- 废止法条警告 -->
    <span
      v-if="!pending && hasValidityWarnings"
      class="inline-flex items-center rounded-full bg-danger/10 px-2 py-0.5 text-[11px] text-danger"
      title="回答引用的法条中可能包含已废止内容"
    >
      ⚠ 含已废止法条
    </span>
  </div>
</template>
