<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { RadarChart as EChartsRadar } from 'echarts/charts'
import { CanvasRenderer } from 'echarts/renderers'
import type { RadarItem } from '@/api/types'

// 按需引入：只打包雷达图 + Canvas 渲染器（包体小约 60%）
echarts.use([EChartsRadar, CanvasRenderer])

const props = defineProps<{
  data: RadarItem[]
  dark?: boolean
}>()

const emit = defineEmits<{ (e: 'select', key: string): void }>()

const el = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null
let resizeObserver: ResizeObserver | null = null

// 半透明蓝填充（stroke-blue-600 系） / 亮色线
const BLUE_600 = '#2563eb'
const BLUE_500_20 = 'rgba(59, 130, 246, 0.2)'
// 深色主题下用亮蓝保证可读
const BLUE_400_DARK = '#4d90d9'
const BLUE_400_20_DARK = 'rgba(77, 144, 217, 0.2)'

function render() {
  if (!chart) return
  const dark = props.dark === true
  const fill = dark ? BLUE_400_20_DARK : BLUE_500_20
  const line = dark ? BLUE_400_DARK : BLUE_600
  const dims = props.data.filter((d) => d.value != null)
  chart.setOption({
    radar: {
      indicator: dims.map((d) => ({ name: d.name, max: 100 })),
      radius: '68%',
      // 网格线/轴线：淡灰色（stroke-slate-200 系）
      splitLine: { lineStyle: { color: dark ? 'rgba(255,255,255,0.15)' : 'rgba(148,163,184,0.4)' } },
      splitArea: { areaStyle: { color: dark ? ['rgba(255,255,255,0.03)'] : ['rgba(59,130,246,0.04)'] } },
      axisLine: { lineStyle: { color: dark ? 'rgba(255,255,255,0.15)' : 'rgba(148,163,184,0.4)' } },
      axisName: { color: dark ? 'rgba(255,255,255,0.75)' : '#64748b', fontSize: 11 },
      triggerEvent: true,
    },
    series: [
      {
        type: 'radar',
        data: [
          {
            value: dims.map((d) => d.value),
            // 数据填充区：半透明蓝（fill-blue-500/20），描边蓝（stroke-blue-600）
            areaStyle: { color: fill },
            lineStyle: { color: line },
            itemStyle: { color: line },
          },
        ],
      },
    ],
  })
}

onMounted(() => {
  if (!el.value) return
  chart = echarts.init(el.value)
  render()
  resizeObserver = new ResizeObserver(() => chart?.resize())
  resizeObserver.observe(el.value)
  // 雷达图点击维度 → 展开对应维度的审计详情
  chart.on('click', (params: unknown) => {
    const p = params as { componentType?: string; name?: string; dimensionIndex?: number }
    if (p.componentType === 'radar' && p.name) {
      const hit = props.data.find((d) => d.name === p.name)
      if (hit) emit('select', hit.key)
    } else if (p.dimensionIndex != null) {
      const dim = props.data.filter((d) => d.value != null)[p.dimensionIndex]
      if (dim) emit('select', dim.key)
    }
  })
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  chart?.dispose()
  chart = null
})

// 数据或主题变化 → 重设 option（暗色切换时图表颜色同步）
watch(() => [props.data, props.dark], render, { deep: true })
</script>

<template>
  <!-- 高度 240px + 圆环半径 68%：给维度标签留足空间，避免重叠 -->
  <div ref="el" class="h-[240px] w-full" />
</template>
