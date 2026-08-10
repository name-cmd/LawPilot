<script setup lang="ts">
import { computed, watch } from 'vue'
import { NTabs, NTabPane, NEmpty, NIcon } from 'naive-ui'
import { ChevronBackOutline } from '@vicons/ionicons5'
import TrustEvalPanel from './TrustEvalPanel.vue'
import ArticleTracePanel from './ArticleTracePanel.vue'
import CitationVerificationPanel from './CitationVerificationPanel.vue'
import ToolTracePanel from './ToolTracePanel.vue'
import { useDetailPanelStore } from '@/stores/detailPanel'
import { useSessionsStore } from '@/stores/sessions'
import { useVerificationWS } from '@/composables/useVerificationWS'
import { isLegalAnalysisMeta, isVerificationPending } from '@/utils/answer'
import type { Message } from '@/stores/sessions'

/**
 * 详情面板统一内容体：桌面侧栏与移动端抽屉共用。
 * 数据来源：detailPanel.selectedMsgId → sessions store 消息对象（WS 推送更新 meta 自动刷新）。
 */

const detail = useDetailPanelStore()
const sessions = useSessionsStore()
const verification = useVerificationWS()

const message = computed<Message | null>(
  () => sessions.sessions.flatMap((s) => s.messages).find((m) => m.id === detail.selectedMsgId) ?? null,
)
const meta = computed(() => message.value?.meta)
const isLegal = computed(() => isLegalAnalysisMeta(meta.value))
const pending = computed(() => isVerificationPending(meta.value))

/**
 * 自愈重连：选中的消息若仍是「核验中」，重连核验 WS 拉取结果。
 * 后端 task_registry 对已完成任务会立即重放结果，因此页面刷新、切会话期间错过
 * 广播的历史卡死消息，点击后一点即恢复；若后端仍在跑，广播到达后照常更新。
 * （核验结果应用走 sessions.applyVerificationResult，跨会话查找，不会丢）
 */
watch(
  () => [detail.selectedMsgId, meta.value?.verification_status] as const,
  ([msgId, status]) => {
    if (!msgId || status !== 'pending') return
    verification.connect(msgId, {
      onComplete: (data) => sessions.applyVerificationResult(msgId, data),
      onError: () => sessions.applyVerificationError(msgId),
    })
  },
)
</script>

<template>
  <div class="flex h-full flex-col overflow-hidden">
    <!-- 头部：「收起」按钮在「详情」左侧，按钮样式醒目（边框+背景），点击收起面板 -->
    <div class="flex h-14 shrink-0 items-center gap-2 border-b border-line px-3">
      <button
        class="flex items-center gap-1 rounded-md border border-line bg-page px-2 py-1 text-[12px] text-muted transition-colors hover:border-brand-400 hover:text-brand-500"
        title="收起详情面板"
        @click="detail.close()"
      >
        <n-icon :component="ChevronBackOutline" size="14" />
        <span>收起</span>
      </button>
      <span class="text-sm font-semibold text-ink">详情</span>
    </div>

    <n-tabs v-model:value="detail.activeTab" type="line" animated class="shrink-0 px-3 pt-1">
      <n-tab-pane name="trust" tab="可信评估" />
      <n-tab-pane name="articles" tab="法条溯源" />
      <n-tab-pane name="verification" tab="引用核验" />
      <n-tab-pane v-if="meta?.tool_trace?.length" name="trace" tab="工具轨迹" />
    </n-tabs>

    <!-- 未选择消息 -->
    <div v-if="!message || !meta || !isLegal" class="flex-1 overflow-y-auto">
      <n-empty
        :description="!message ? '提问后自动展示可信评估详情' : '非法律类回答无可信评估'"
        class="pt-16"
      />
    </div>

    <!-- 已选择法律类消息 -->
    <div v-else class="flex-1 space-y-4 overflow-y-auto px-3 pb-4">
      <TrustEvalPanel
        v-if="detail.activeTab === 'trust'"
        :trust="meta.trust ?? null"
        :pending="pending"
        :meta="meta"
        @jump="detail.jumpTo"
      />
      <ArticleTracePanel
        v-else-if="detail.activeTab === 'articles'"
        :articles="meta.retrieved_articles || []"
      />
      <ToolTracePanel
        v-else-if="detail.activeTab === 'trace'"
        :steps="meta.tool_trace || []"
      />
      <CitationVerificationPanel
        v-else
        :pending="pending"
        :verification="meta.citation_verification || null"
        :regeneration-attempts="meta.regeneration_attempts || 0"
      />
    </div>
  </div>
</template>
