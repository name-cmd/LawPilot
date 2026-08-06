<script setup lang="ts">
import { computed } from 'vue'
import { NIcon } from 'naive-ui'
import { CheckmarkCircleOutline, ScaleOutline, BookOutline } from '@vicons/ionicons5'
import MarkdownRenderer from '@/components/common/MarkdownRenderer.vue'
import { parseAnswerSections } from '@/utils/answer'

const props = defineProps<{
  content: string
  /** 流式中：渲染纯文本 + 打字光标；完成后才切章节/Markdown */
  streaming: boolean
}>()

const sections = computed(() => (props.streaming ? null : parseAnswerSections(props.content)))
</script>

<template>
  <!-- 流式阶段：纯文本 + 打字光标（避免每个 token 都跑 Markdown 解析） -->
  <div v-if="streaming" class="whitespace-pre-wrap leading-relaxed">
    {{ content }}<span class="animate-blink font-semibold text-blue-600">▍</span>
  </div>

  <!-- 三段式章节渲染（后端回答带【结论】【法律分析】【依据法条】）。
       统一为纯文字章节：无方框、无底色，标题同一样式（带小图标），正文直接浮在卡片白底上 -->
  <div v-else-if="sections" class="space-y-3">
    <template v-for="sec in sections" :key="sec.title">
      <!-- 【结论】：对勾圆图标，表示结论确认 -->
      <section v-if="sec.title === '结论'" class="leading-[1.7]">
        <div class="mb-1.5 flex items-center gap-1.5">
          <n-icon :component="CheckmarkCircleOutline" size="16" class="text-brand-500" />
          <h3 class="text-sm font-semibold text-ink">结论</h3>
        </div>
        <MarkdownRenderer :content="sec.body" class="text-sm text-ink" />
      </section>

      <!-- 【法律分析】：天平图标，法律分析；标准 Markdown 排版，行高 1.7 -->
      <section v-else-if="sec.title === '法律分析'" class="leading-[1.7]">
        <div class="mb-1.5 flex items-center gap-1.5">
          <n-icon :component="ScaleOutline" size="16" class="text-brand-500" />
          <h3 class="text-sm font-semibold text-ink">法律分析</h3>
        </div>
        <MarkdownRenderer :content="sec.body" class="text-sm text-ink" />
      </section>

      <!-- 【依据法条】：法典图标，与结论/法律分析同款样式 -->
      <section v-else class="leading-[1.7]">
        <div class="mb-1.5 flex items-center gap-1.5">
          <n-icon :component="BookOutline" size="16" class="text-brand-500" />
          <h3 class="text-sm font-semibold text-ink">依据法条</h3>
        </div>
        <MarkdownRenderer :content="sec.body" class="text-sm text-ink" />
      </section>
    </template>
  </div>

  <!-- 无章节结构：整体 Markdown 渲染 -->
  <MarkdownRenderer v-else :content="content" class="text-sm text-ink" />
</template>
