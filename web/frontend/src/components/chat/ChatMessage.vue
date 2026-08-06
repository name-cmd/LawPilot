<script setup lang="ts">
import { computed } from 'vue'
import { useMessage } from 'naive-ui'
import AnswerContent from './AnswerContent.vue'
import ThinkingBubble from './ThinkingBubble.vue'
import { useDetailPanelStore } from '@/stores/detailPanel'
import { useFavoritesStore } from '@/stores/favorites'
import { isLegalAnalysisMeta } from '@/utils/answer'
import type { Message } from '@/stores/sessions'

const props = defineProps<{ message: Message }>()

const detail = useDetailPanelStore()
const favorites = useFavoritesStore()
const toast = useMessage()

const isUser = computed(() => props.message.role === 'user')
/** 是否正在流式生成（loading 且已有部分内容，或 thinkingText 已切换为生成中） */
const streaming = computed(() => Boolean(props.message.loading) && !props.message.refusal)
/** 法律类回答可点击打开详情面板 */
const clickable = computed(() => !isUser.value && isLegalAnalysisMeta(props.message.meta))
/** 当前被详情面板选中的消息（高亮边框） */
const selected = computed(() => detail.selectedMsgId === props.message.id)
/** 是否已收藏 */
const fav = computed(() => favorites.isFavorited(props.message.id))

/** 收藏/取消收藏（数据快照进 favorites store，跨会话可查） */
function onToggleFav() {
  const result = favorites.toggleFavorite(props.message.id)
  if (result === 'added') toast.success('已收藏')
  else if (result === 'removed') toast.info('已取消收藏')
}
</script>

<template>
  <div class="flex animate-fade-in-up gap-3" :class="isUser ? 'justify-end' : 'justify-start'">
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

      <!-- 底部操作栏（核验状态 + 收藏；拒答消息不显示） -->
      <div
        v-if="message.content && !message.loading && !message.refusal"
        class="mt-1.5 flex items-center gap-2 px-1 text-[11px] text-muted"
      >
        <span v-if="message.meta?.verification_status === 'pending'" class="text-warning">
          引用核验中…
        </span>
        <span v-else-if="message.meta?.verification_status === 'complete'">
          已核验
        </span>
        <button
          class="transition-colors hover:text-warning"
          :class="fav ? 'text-warning' : ''"
          @click="onToggleFav"
        >
          {{ fav ? '★ 已收藏' : '☆ 收藏' }}
        </button>
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
        <div class="rounded-xl bg-[#EDF3FE] px-3 py-2.5 text-slate-800 shadow-soft">
          <AnswerContent v-if="!message.refusal" :content="message.content" :streaming="streaming" />
        </div>
      </div>
    </template>
  </div>
</template>
