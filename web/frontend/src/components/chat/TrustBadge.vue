<script setup lang="ts">
import { computed } from 'vue'
import type { MessageMeta } from '@/api/types'
import { isLegalAnalysisMeta } from '@/utils/answer'

/**
 * 废止法条警告（AI 回复卡片底部操作栏左侧）：
 * 引用核验发现回答引用的法条可能已废止时，显示黄色警告条。
 * （原「★ 综合可信分」徽章与核验中徽章已于 2026-08-09 按需求移除；
 *  核验中状态由操作栏的「引用核验中…」文字提示）
 */
const props = defineProps<{ meta?: MessageMeta }>()

const legal = computed(() => isLegalAnalysisMeta(props.meta))
const hasValidityWarnings = computed(() => Boolean(props.meta?.validity_warnings?.length))
</script>

<template>
  <!-- 废止法条警告 -->
  <span
    v-if="legal && hasValidityWarnings"
    class="inline-flex items-center rounded-full bg-danger/10 px-2 py-0.5 text-[11px] text-danger"
    title="回答引用的法条中可能包含已废止内容"
  >
    ⚠ 含已废止法条
  </span>
</template>
