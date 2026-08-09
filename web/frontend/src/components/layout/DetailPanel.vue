<script setup lang="ts">
import { NIcon } from 'naive-ui'
import { ChevronBackOutline } from '@vicons/ionicons5'
import DetailBody from '@/components/detail/DetailBody.vue'
import { useDetailPanelStore } from '@/stores/detailPanel'

/**
 * 详情面板容器：普通 flex 侧栏，所有视口宽度常驻显示。
 * 不用抽屉/浮层 —— 抽屉容器是全屏 fixed 定位，会造成遮罩、点击拦截、
 * 收起后聊天区不变宽等问题（已反复出现）。
 * 收起（v-show=false）后面板让出空间，聊天区 flex-1 自动变宽；
 * 此时右侧边缘中部悬浮一个半圆展开按钮（fixed 贴屏幕右缘，不遮挡聊天内容），
 * 点击重新展开面板 —— 从哪收起就从哪打开，符合直觉。
 * 内容统一由 DetailBody 渲染（数据源：detailPanel store → sessions 消息 meta）。
 */
const detail = useDetailPanelStore()
</script>

<template>
  <!-- 右侧评估面板：固定 340px 白底 -->
  <aside
    v-show="detail.isOpen"
    class="w-[340px] shrink-0 border-l border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800"
  >
    <DetailBody />
  </aside>

  <!-- 收起后的展开按钮：半圆 tab 贴屏幕右缘、垂直居中，hover 变品牌蓝 -->
  <button
    v-if="!detail.isOpen"
    class="fixed right-0 top-1/2 z-40 flex h-24 w-6 -translate-y-1/2 cursor-pointer items-center justify-center rounded-l-lg border border-r-0 border-slate-200 bg-white text-slate-400 shadow-md transition-colors hover:text-brand-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400 dark:hover:text-blue-400"
    title="展开详情面板"
    @click="detail.openWithLatest()"
  >
    <n-icon :component="ChevronBackOutline" size="16" />
  </button>
</template>
