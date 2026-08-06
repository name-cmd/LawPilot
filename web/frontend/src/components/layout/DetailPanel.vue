<script setup lang="ts">
import DetailBody from '@/components/detail/DetailBody.vue'
import { useDetailPanelStore } from '@/stores/detailPanel'

/**
 * 详情面板容器：普通 flex 侧栏，所有视口宽度常驻显示。
 * 不用抽屉/浮层 —— 抽屉容器是全屏 fixed 定位，会造成遮罩、点击拦截、
 * 收起后聊天区不变宽等问题（已反复出现）。
 * 收起（v-show=false）后面板让出空间，聊天区 flex-1 自动变宽。
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
</template>
