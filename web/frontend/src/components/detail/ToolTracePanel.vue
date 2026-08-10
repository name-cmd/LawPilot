<script setup lang="ts">
import type { ToolTraceStep } from '@/api/types'

defineProps<{ steps: ToolTraceStep[] }>()
</script>

<template>
  <div class="space-y-3">
    <div v-if="!steps.length" class="px-1 pt-10 text-center text-[12px] text-muted">
      本次回答未调用工具
    </div>
    <div
      v-for="s in steps"
      :key="`${s.step}-${s.tool_name}`"
      class="rounded-xl border border-line bg-surface p-3"
    >
      <div class="flex items-center gap-2 text-[12px]">
        <span class="font-medium text-ink">第 {{ s.step }} 轮</span>
        <span class="rounded bg-page px-1.5 py-0.5 font-medium text-brand-500">{{ s.tool_name }}</span>
        <span :class="s.success ? 'text-success' : 'text-danger'">
          {{ s.success ? '✓ 成功' : '✗ 失败' }}
        </span>
        <span class="ml-auto text-muted">{{ s.cost_ms }} ms</span>
      </div>
      <div v-if="Object.keys(s.arguments).length" class="mt-2 break-all text-[11px] text-muted">
        参数：{{ JSON.stringify(s.arguments) }}
      </div>
      <div class="mt-1 text-[12px] text-muted">{{ s.result_summary }}</div>
    </div>
  </div>
</template>
