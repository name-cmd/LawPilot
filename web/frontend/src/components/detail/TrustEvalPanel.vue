<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import RadarChart from './RadarChart.vue'
import { useDetailPanelStore } from '@/stores/detailPanel'
import { useSettingsStore } from '@/stores/settings'
import type { DimensionDetail, TrustResult } from '@/api/types'
import type { MessageMeta } from '@/api/types'

const props = defineProps<{ trust: TrustResult | null; pending: boolean; meta: MessageMeta }>()
/** 跳转 tab（后端 detail_ref 用 citations，映射为面板 verification） */
const emit = defineEmits<{ (e: 'jump', tab: 'articles' | 'verification'): void }>()

const detail = useDetailPanelStore()
const settings = useSettingsStore()

// ── 信任环（SVG 圆弧进度） ──
const ringPct = computed(() => {
  const s = props.trust?.overall_score
  if (s == null) return 0
  return Math.min(100, Math.max(0, s))
})
const ringCirc = 2 * Math.PI * 40
const ringOffset = computed(() => ringCirc - (ringPct.value / 100) * ringCirc)
const ringColor = computed(() => {
  const s = props.trust?.overall_score
  if (s == null) return '#9ca3af'
  if (s >= 85) return '#2ec27e'
  if (s >= 70) return '#1a5fb4'
  return '#e5a50a'
})

// ── 短评（信任环下方一行）：可信等级 · N 处法条已核验 ──
const headline = computed(() => {
  const level = props.trust?.trust_level || '未评估'
  const citeCount = props.meta.citation_verification?.extracted_citations?.length || 0
  return citeCount ? `${level} · ${citeCount} 处法条已核验` : level
})

// ── 维度颜色 ──
function dimScoreClass(score: number | null) {
  if (score == null) return 'text-muted'
  if (score >= 85) return 'text-success'
  if (score >= 70) return 'text-brand-500'
  return 'text-warning'
}
function dimBarColor(score: number | null) {
  if (score == null) return '#9ca3af'
  if (score >= 85) return '#2ec27e'
  if (score >= 70) return '#1a5fb4'
  return '#e5a50a'
}

// ── 维度展开态：切换消息时重置为最弱维度（旧版 lastTrustMsgId 语义） ──
const expandedDimKey = ref<string | null>(null)
watch(
  () => detail.selectedMsgId,
  () => {
    expandedDimKey.value = props.trust?.weak_dimensions?.[0]?.key ?? null
  },
)
watch(
  () => props.trust?.overall_score,
  () => {
    // 核验完成（overall_score 从 null 变数值）时展开最弱维度
    if (props.trust?.overall_score != null) {
      expandedDimKey.value = props.trust?.weak_dimensions?.[0]?.key ?? null
    }
  },
)

function toggleDim(key: string) {
  expandedDimKey.value = expandedDimKey.value === key ? null : key
}

// ── 检查 chips 文案（旧版 renderDimChecks 语义） ──
function checkText(c: DimensionDetail['checks'][number]) {
  if (typeof c.passed === 'number' && c.total && c.total > 1 && c.type !== 'consistency') {
    return `${c.label} ${c.passed}/${c.total}`
  }
  if (c.type === 'consistency' && typeof c.passed === 'number') {
    return `${c.label} ${c.passed}%`
  }
  return c.label
}
function checkSeverity(c: DimensionDetail['checks'][number]) {
  if (c.severity && c.severity !== 'ok') return c.severity
  if (typeof c.passed === 'number' && c.total && c.passed < c.total) return 'warning'
  return 'ok'
}

// ── 公式审计（旧版 renderFormulaBlock 语义） ──
function formulaText(f: NonNullable<DimensionDetail['formula']>) {
  const inputs = (f.inputs || []).map((i) => `${i.name} ${i.value}×${i.weight}`).join(' + ')
  return `${inputs}${f.result != null ? ` = ${f.result}` : ''}`
}

// ── hero 元信息行 ──
const heroMetaParts = computed(() => {
  const parts: string[] = []
  if (props.trust?.evaluated_at) parts.push(`评估 ${props.trust.evaluated_at}`)
  const citeCount = props.meta.citation_verification?.extracted_citations?.length || 0
  if (citeCount) parts.push(`${citeCount} 处引用已核验`)
  const articleCount = props.meta.retrieved_articles?.length || 0
  if (articleCount) parts.push(`${articleCount} 条法条溯源`)
  return parts
})

// 贡献分解条宽度：以最大贡献为基准（旧版 maxContrib 语义）
const maxContribution = computed(() =>
  Math.max(...(props.trust?.score_contributions || []).map((r) => r.contribution || 0), 1),
)

// 维度列表跳转按钮（后端 detail_ref 的 citations 映射为面板 verification tab）
function dimJumpButtons(d: DimensionDetail) {
  const btns: { tab: 'articles' | 'verification'; label: string }[] = []
  if (d.detail_ref === 'citations') btns.push({ tab: 'verification', label: '查看引用核验 →' })
  if (d.detail_ref === 'articles' || d.key === 'truthfulness') {
    btns.push({ tab: 'articles', label: '查看法条溯源 →' })
  }
  return btns
}
</script>

<template>
  <div class="space-y-3">
    <!-- 核验中横幅 -->
    <div v-if="pending" class="rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-[12px] text-warning">
      可信度分析核验中…
    </div>

    <!-- 总分（大字号信任环）+ 短评 + 建议 -->
    <div class="flex items-center gap-3">
      <div class="relative h-24 w-24 shrink-0">
        <svg viewBox="0 0 96 96" class="h-full w-full -rotate-90">
          <circle cx="48" cy="48" r="40" fill="none" stroke="var(--color-line)" stroke-width="6" />
          <circle
            cx="48" cy="48" r="40" fill="none"
            :stroke="ringColor" stroke-width="6" stroke-linecap="round"
            :stroke-dasharray="ringCirc" :stroke-dashoffset="ringOffset"
            class="transition-all duration-700"
          />
        </svg>
        <div class="absolute inset-0 flex items-center justify-center text-3xl font-bold text-ink">
          {{ trust?.overall_score ?? '…' }}
        </div>
      </div>

      <div class="min-w-0 flex-1">
        <!-- 短评：可信等级 · 引用核验数量 -->
        <div class="text-[13px] font-semibold text-slate-700 dark:text-slate-200">
          {{ pending ? '核验中 · 初步回答已生成' : headline }}
        </div>
        <p class="mt-1 text-[12px] leading-relaxed text-muted">
          {{ pending ? '完整评估进行中，稍后自动刷新…' : trust?.advice || '' }}
        </p>
        <!-- 弱维度标签 -->
        <div v-if="trust?.weak_dimensions?.length" class="mt-1 flex flex-wrap gap-1">
          <span
            v-for="w in trust.weak_dimensions" :key="w.label"
            class="rounded bg-danger/10 px-1.5 py-0.5 text-[10px] text-danger"
          >
            {{ w.label }} {{ w.score }}
          </span>
        </div>
      </div>
    </div>

    <!-- 元信息行 -->
    <div v-if="heroMetaParts.length" class="text-[11px] text-muted">
      {{ heroMetaParts.join(' · ') }}
    </div>

    <!-- 加权贡献分解（核验完成才有） -->
    <div v-if="!pending && trust?.score_contributions?.length" class="rounded-xl border border-line bg-surface p-3">
      <div class="mb-2 text-[12px] font-semibold text-ink">加权贡献</div>
      <div class="space-y-1.5">
        <div v-for="r in trust.score_contributions" :key="r.label" class="flex items-center gap-2">
          <span class="w-16 shrink-0 text-[11px] text-slate-500 dark:text-slate-400">{{ r.label }}</span>
          <div class="h-2 flex-1 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-700">
            <div
              class="h-full rounded-full bg-gradient-to-r from-blue-500/60 to-green-500/60 transition-all duration-500"
              :style="{ width: `${((r.contribution || 0) / maxContribution) * 100}%` }"
            />
          </div>
          <span class="w-10 shrink-0 text-right text-[12px] font-semibold text-blue-600 dark:text-blue-400">
            +{{ r.contribution ?? '—' }}
          </span>
        </div>
        <div class="flex items-center justify-between border-t border-line pt-1.5 text-[11px]">
          <span class="text-muted">综合可信分</span>
          <span class="font-semibold text-ink">{{ trust.overall_score ?? '…' }}</span>
        </div>
      </div>
    </div>

    <!-- 雷达图（暗色适配：settings store 主题驱动） -->
    <RadarChart
      v-if="trust?.radar_data?.length"
      :data="trust.radar_data"
      :dark="settings.theme === 'dark'"
      @select="toggleDim"
    />

    <!-- 六维列表 -->
    <div v-if="trust?.dimension_details?.length" class="space-y-1">
      <div
        v-for="d in trust.dimension_details" :key="d.key"
        class="rounded-xl border border-line bg-surface transition-colors"
        :class="d.score != null && d.score < 70 ? 'border-danger/30' : ''"
      >
        <!-- 维度头部：点击展开 -->
        <button
          class="flex w-full items-center gap-2 px-3 py-2 text-left"
          @click="toggleDim(d.key)"
        >
          <span class="flex-1 truncate text-[12px] font-medium text-ink">
            {{ d.label }}
            <span class="ml-1 text-[10px] text-muted">{{ (d.weight * 100).toFixed(0) }}%</span>
          </span>
          <span class="h-1 w-12 overflow-hidden rounded-full bg-line">
            <span
              class="block h-full rounded-full"
              :style="{ width: `${Math.min(d.score ?? 0, 100)}%`, background: dimBarColor(d.score) }"
            />
          </span>
          <span class="w-8 text-right text-[12px] font-semibold" :class="dimScoreClass(d.score)">
            {{ d.score ?? '…' }}
          </span>
          <span class="text-[10px] text-muted">{{ expandedDimKey === d.key ? '▲' : '▼' }}</span>
        </button>

        <!-- 展开的审计详情 -->
        <div v-if="expandedDimKey === d.key" class="space-y-2 border-t border-line px-3 py-2">
          <span
            class="inline-block rounded px-1.5 py-0.5 text-[10px]"
            :class="d.status === 'pending' || d.pending ? 'bg-warning/10 text-warning' : 'bg-success/10 text-success'"
          >
            {{ d.status === 'pending' || d.pending ? '核验中' : '已核验' }}
          </span>
          <p class="text-[12px] leading-relaxed text-muted">
            {{ d.evidence_summary || d.method || '无摘要' }}
          </p>

          <!-- 检查 chips -->
          <div v-if="d.checks?.length" class="flex flex-wrap gap-1">
            <span
              v-for="(c, i) in d.checks" :key="i"
              class="rounded px-1.5 py-0.5 text-[10px]"
              :class="
                checkSeverity(c) === 'warning'
                  ? 'bg-warning/10 text-warning'
                  : checkSeverity(c) === 'error'
                    ? 'bg-danger/10 text-danger'
                    : 'bg-success/10 text-success'
              "
            >
              {{ checkText(c) }}
            </span>
          </div>

          <!-- 公式审计 -->
          <div v-if="d.formula?.expression" class="rounded-lg bg-page px-2.5 py-1.5 text-[11px] text-muted">
            <div class="font-medium text-ink">{{ d.formula.expression }}</div>
            <div>{{ formulaText(d.formula) }}</div>
          </div>

          <!-- 跳转按钮 -->
          <div v-if="dimJumpButtons(d).length" class="flex gap-2">
            <button
              v-for="b in dimJumpButtons(d)" :key="b.tab"
              class="text-[11px] text-brand-500 hover:underline"
              @click="emit('jump', b.tab)"
            >
              {{ b.label }}
            </button>
          </div>

          <!-- 完整审计说明折叠 -->
          <details v-if="d.evidence?.length" class="text-[11px] text-muted">
            <summary class="cursor-pointer hover:text-ink">查看完整审计说明</summary>
            <ul class="mt-1 list-disc space-y-1 pl-4">
              <li v-for="(e, i) in d.evidence" :key="i">{{ e }}</li>
            </ul>
          </details>
        </div>
      </div>
    </div>
  </div>
</template>
