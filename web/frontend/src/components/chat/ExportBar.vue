<script setup lang="ts">
import { NButton } from 'naive-ui'

/**
 * 导出模式操作栏（legacy .export-bar 语义）：
 * 全选法律问答 + 已选计数 + 导出按钮（未选时禁用）+ 取消。
 */
defineProps<{
  /** 已勾选条数 */
  selectedCount: number
  /** 可导出总条数 */
  totalCount: number
  /** 是否全选（「全选法律问答」复选框状态） */
  allSelected: boolean
}>()

const emit = defineEmits<{ 'toggle-all': [checked: boolean]; export: []; cancel: [] }>()
</script>

<template>
  <div
    class="flex shrink-0 items-center gap-3 border-b border-blue-200 bg-blue-50 px-4 py-2.5 text-[13px] dark:border-slate-700 dark:bg-slate-800"
  >
    <label class="flex cursor-pointer select-none items-center gap-1.5 text-slate-700 dark:text-slate-200">
      <input
        type="checkbox"
        class="size-4 accent-blue-600"
        :checked="allSelected"
        @change="emit('toggle-all', ($event.target as HTMLInputElement).checked)"
      />
      全选法律问答
    </label>
    <span class="text-slate-500 dark:text-slate-400">已选 {{ selectedCount }} 条</span>
    <n-button
      size="small"
      type="primary"
      class="ml-auto"
      :disabled="selectedCount === 0"
      @click="emit('export')"
    >
      导出可信评估报告
    </n-button>
    <n-button size="small" quaternary @click="emit('cancel')">取消</n-button>
  </div>
</template>
