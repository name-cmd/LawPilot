<script setup lang="ts">
import { computed } from 'vue'
import { NIcon, useMessage } from 'naive-ui'
import {
  CopyOutline,
  RefreshOutline,
  SparklesOutline,
  Star,
  StarOutline,
  ThumbsDown,
  ThumbsDownOutline,
  ThumbsUp,
  ThumbsUpOutline,
} from '@vicons/ionicons5'
import AnswerContent from './AnswerContent.vue'
import ThinkingBubble from './ThinkingBubble.vue'
import TrustBadge from './TrustBadge.vue'
import { useDetailPanelStore } from '@/stores/detailPanel'
import { useFavoritesStore } from '@/stores/favorites'
import { useSessionsStore } from '@/stores/sessions'
import { imgError, modelLogo } from '@/utils/modelLogo'
import { isLegalAnalysisMeta } from '@/utils/answer'
import type { Message } from '@/stores/sessions'

const props = defineProps<{
  message: Message
  /** 导出模式下显示法律回答的勾选复选框 */
  exportMode?: boolean
  exportChecked?: boolean
}>()

const emit = defineEmits<{ 'toggle-export': [checked: boolean]; regenerate: [] }>()

const detail = useDetailPanelStore()
const favorites = useFavoritesStore()
const sessions = useSessionsStore()
const toast = useMessage()

const isUser = computed(() => props.message.role === 'user')
/** 是否正在流式生成（loading 且已有部分内容，或 thinkingText 已切换为生成中） */
const streaming = computed(() => Boolean(props.message.loading) && !props.message.refusal)
/** 法律类回答可点击打开详情面板 */
const clickable = computed(() => !isUser.value && isLegalAnalysisMeta(props.message.meta))
/** 可导出：助手消息 + 已生成完成 + 法律类（loading/拒答不可导出） */
const exportable = computed(
  () => !isUser.value && !props.message.loading && isLegalAnalysisMeta(props.message.meta),
)
/** 当前被详情面板选中的消息（高亮边框） */
const selected = computed(() => detail.selectedMsgId === props.message.id)
/** 是否已收藏 */
const fav = computed(() => favorites.isFavorited(props.message.id))

/**
 * 左下角模型角标：Auto 模式下显示「Auto」（发起时快照 requested_model==='auto'），
 * 不显示后端解析后的实际模型名；悬停 title 里保留实际使用的模型，信息不丢失。
 * 历史消息（无 requested_model 字段）按实际模型名显示，行为不变。
 */
const modelBadgeText = computed(() =>
  props.message.meta?.requested_model === 'auto' ? 'Auto' : props.message.meta?.model_name,
)
const modelBadgeTitle = computed(() => {
  const meta = props.message.meta
  if (!meta) return ''
  return meta.requested_model === 'auto'
    ? `Auto · 实际使用 ${meta.model_name ?? meta.model_id ?? ''}`
    : meta.model_id || meta.model_name || ''
})
/** Auto 模式标识：发起时快照 requested_model==='auto' 时，与模型选择器一致显示
    星光渐变图标（不绑定任何供应商品牌）；具体模型才显示品牌 logo */
const modelBadgeIsAuto = computed(() => props.message.meta?.requested_model === 'auto')
/** 模型品牌 logo：按实际使用的 model_id 映射（仅具体模型；Auto 显示星光图标） */
const modelBadgeLogo = computed(() =>
  modelBadgeIsAuto.value ? undefined : modelLogo(props.message.meta?.model_id),
)

/** 收藏/取消收藏（数据快照进 favorites store，跨会话可查） */
function onToggleFav() {
  const result = favorites.toggleFavorite(props.message.id)
  if (result === 'added') toast.success('已收藏')
  else if (result === 'removed') toast.info('已取消收藏')
}

/** 当前反馈评级（up/down；未反馈为 undefined） */
const fbRating = computed(() => props.message.feedback?.rating)

/** 点赞/点踩：记录进消息的 feedback 字段（随会话持久化到 localStorage，无后端接口）；
    再次点击同一按钮取消反馈 */
function onFeedback(rating: 'up' | 'down') {
  if (fbRating.value === rating) {
    sessions.updateMessage(props.message.id, { feedback: undefined })
    toast.info('已取消反馈')
  } else {
    sessions.updateMessage(props.message.id, { feedback: { rating } })
    toast.success(rating === 'up' ? '感谢反馈' : '已记录反馈，我们会持续改进')
  }
}

/** 复制回答全文到剪贴板（navigator.clipboard 需安全上下文，失败时提示手动复制） */
function onCopy() {
  navigator.clipboard
    .writeText(props.message.content)
    .then(() => toast.success('已复制到剪贴板'))
    .catch(() => toast.error('复制失败，请手动选择复制'))
}
</script>

<template>
  <div class="flex animate-fade-in-up gap-3" :class="isUser ? 'justify-end' : 'justify-start'">
    <!-- 导出模式勾选：法律助手消息前显示（卡片的兄弟节点，点击不冒泡到卡片选中） -->
    <input
      v-if="exportMode && exportable"
      type="checkbox"
      class="mt-6 size-4 shrink-0 cursor-pointer accent-blue-600"
      :checked="exportChecked"
      @change="emit('toggle-export', ($event.target as HTMLInputElement).checked)"
    />
    <!-- AI 回复：单层白底卡片（头像/名称/评分徽章在卡片头部，告别外层套娃） -->
    <div v-if="!isUser" class="min-w-0 max-w-[min(900px,88%)]">
      <!-- min(900px, 88%)：卡片宽度跟随聊天区（收起详情面板后变宽），上限 900px 保证可读性 -->
      <div
        class="rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm transition-colors dark:border-slate-700 dark:bg-slate-800"
        :class="(clickable ? 'cursor-pointer hover:border-blue-400' : '') + (selected ? ' border-blue-400 ring-1 ring-blue-400/40' : '')"
        @click="clickable && detail.selectMessage(message.id)"
      >
        <!-- 思考中：卡片内文字 + 呼吸点 -->
        <div v-if="message.loading && !message.content" class="text-sm text-muted">
          <span v-if="message.thinkingText" class="mr-2">{{ message.thinkingText }}</span>
          <ThinkingBubble class="inline-flex" />
        </div>

        <!-- 回答内容（拒答消息走下面的提示条，不重复渲染） -->
        <AnswerContent
          v-if="!message.refusal"
          :content="message.content"
          :streaming="streaming"
        />

        <!-- 安全拒答提示条 -->
        <div
          v-if="message.refusal"
          class="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          {{ message.content }}
        </div>
      </div>

      <!-- 底部操作栏（废止警告 + 模型名[带品牌 logo] + 核验状态 + 图标按钮组；拒答消息不显示） -->
      <div
        v-if="message.content && !message.loading && !message.refusal"
        class="mt-1.5 flex flex-wrap items-center gap-2 px-1 text-[11px] text-muted"
      >
        <!-- 废止法条警告（原「★ 综合可信分」徽章已移除） -->
        <TrustBadge :meta="message.meta" />
        <!-- 模型角标：logo + 名称；Auto 模式下显示「Auto」+ 星光渐变图标
             （与模型选择器的 Auto 标识一致，不绑定具体品牌），悬停可见实际使用的模型 -->
        <span
          v-if="modelBadgeText"
          class="inline-flex items-center gap-1 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500 dark:bg-slate-700/60 dark:text-slate-400"
          :title="modelBadgeTitle"
        >
          <span
            v-if="modelBadgeIsAuto"
            class="flex h-3 w-3 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-400 to-purple-500"
          >
            <n-icon :component="SparklesOutline" size="7" class="text-white" />
          </span>
          <img
            v-else-if="modelBadgeLogo"
            :src="modelBadgeLogo"
            class="h-3 w-3 rounded-full object-contain"
            @error="imgError"
          />
          {{ modelBadgeText }}
        </span>
        <!-- 核验状态：核验中提示；完成后不再显示任何字样 -->
        <span v-if="message.meta?.verification_status === 'pending'" class="text-warning">
          引用核验中…
        </span>

        <!-- 操作按钮组：仅图标，悬停显示功能提示（参考 FontAwesome 风格：浅灰圆角容器、
             透明按钮，hover 灰底加深色） -->
        <div
          class="ml-auto flex items-center gap-0.5 rounded-lg bg-slate-100/80 px-1.5 py-1 dark:bg-slate-700/50"
        >
          <!-- 点赞（选中绿色实心，再点一次取消） -->
          <button
            class="flex items-center justify-center rounded p-1 text-slate-400 transition-all hover:bg-slate-200 dark:hover:bg-slate-600"
            :class="fbRating === 'up' ? 'text-green-600' : 'hover:text-slate-600 dark:hover:text-slate-200'"
            title="有帮助"
            @click="onFeedback('up')"
          >
            <n-icon :component="fbRating === 'up' ? ThumbsUp : ThumbsUpOutline" :size="14" />
          </button>
          <!-- 点踩（选中红色实心，再点一次取消） -->
          <button
            class="flex items-center justify-center rounded p-1 text-slate-400 transition-all hover:bg-slate-200 dark:hover:bg-slate-600"
            :class="fbRating === 'down' ? 'text-red-500' : 'hover:text-slate-600 dark:hover:text-slate-200'"
            title="需改进"
            @click="onFeedback('down')"
          >
            <n-icon :component="fbRating === 'down' ? ThumbsDown : ThumbsDownOutline" :size="14" />
          </button>
          <!-- 复制回答全文 -->
          <button
            class="flex items-center justify-center rounded p-1 text-slate-400 transition-all hover:bg-slate-200 hover:text-slate-600 dark:hover:bg-slate-600 dark:hover:text-slate-200"
            title="复制回答"
            @click="onCopy"
          >
            <n-icon :component="CopyOutline" :size="14" />
          </button>
          <!-- 重新生成：移除本条回答后按原问题重跑 -->
          <button
            class="flex items-center justify-center rounded p-1 text-slate-400 transition-all hover:bg-slate-200 hover:text-slate-600 dark:hover:bg-slate-600 dark:hover:text-slate-200"
            title="重新生成回答"
            @click="emit('regenerate')"
          >
            <n-icon :component="RefreshOutline" :size="14" />
          </button>
          <!-- 收藏（选中黄色实心） -->
          <button
            class="flex items-center justify-center rounded p-1 text-slate-400 transition-all hover:bg-slate-200 dark:hover:bg-slate-600"
            :class="fav ? 'text-warning' : 'hover:text-slate-600 dark:hover:text-slate-200'"
            :title="fav ? '取消收藏' : '收藏'"
            @click="onToggleFav"
          >
            <n-icon :component="fav ? Star : StarOutline" :size="14" />
          </button>
        </div>
      </div>
    </div>

    <!-- 用户消息：气泡（右侧）+ 头像（最右侧） -->
    <template v-else>
      <div class="min-w-0 max-w-[min(900px,88%)]">
        <!-- 用户附件 chips -->
        <div v-if="message.attachments?.length" class="mb-2 flex flex-wrap gap-1.5">
          <span
            v-for="a in message.attachments"
            :key="a.filename"
            class="rounded-md bg-white/20 px-2 py-0.5 text-[11px]"
          >
            📄 {{ a.filename }}（{{ a.char_count }} 字）
          </span>
        </div>
        <div class="rounded-xl bg-[#EDF3FE] px-3 py-2.5 text-slate-800 shadow-soft dark:bg-slate-700 dark:text-slate-100">
          <AnswerContent v-if="!message.refusal" :content="message.content" :streaming="streaming" />
        </div>
      </div>
    </template>
  </div>
</template>
