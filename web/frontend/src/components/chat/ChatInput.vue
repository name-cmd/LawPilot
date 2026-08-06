<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { NButton, NIcon, NSwitch } from 'naive-ui'
import { SendOutline, StopOutline } from '@vicons/ionicons5'
import { useSettingsStore } from '@/stores/settings'

const settings = useSettingsStore()

const input = ref('')
const textareaRef = ref<HTMLTextAreaElement | null>(null)

const props = defineProps<{
  /** 是否有问答请求进行中：true 时发送按钮变为「停止」 */
  streaming?: boolean
}>()

const emit = defineEmits<{ send: []; cancel: [] }>()

function send() {
  if (!input.value.trim() || props.streaming) return
  emit('send')
}

function onKeydown(e: KeyboardEvent) {
  // Enter 发送，Shift+Enter 换行（旧版行为）
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}

function autoGrow() {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 160) + 'px'
}

// ── 对外暴露：ChatView（ask 流程 / 欢迎页示例）通过 ref 调用 ──
function getInput(): string {
  return input.value
}
function setInput(v: string) {
  input.value = v
  nextTick(autoGrow)
}
function clearInput() {
  input.value = ''
  nextTick(autoGrow)
}
function focus() {
  nextTick(() => textareaRef.value?.focus())
}

defineExpose({ getInput, setInput, clearInput, focus })
</script>

<template>
  <!-- 悬浮输入区：满宽白卡，左右边缘与上方消息气泡（贴左/贴右）对齐；
       收起右侧评估面板时随 flex 自适应同步变宽 -->
  <div class="px-4 pb-4 pt-2">
    <div
      class="w-full overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-lg transition-shadow focus-within:border-blue-400 focus-within:shadow-xl dark:border-slate-700 dark:bg-slate-800"
    >
      <!-- 输入行 -->
      <div class="flex items-end gap-2 px-3 pt-2">
        <textarea
          ref="textareaRef"
          v-model="input"
          rows="1"
          placeholder="输入您的法律问题，回车发送（Shift+Enter 换行）"
          class="max-h-40 flex-1 resize-none bg-transparent px-1 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none dark:text-slate-100"
          @keydown="onKeydown"
          @input="autoGrow"
        />
        <n-button
          v-if="streaming"
          type="error"
          quaternary
          round
          title="停止生成"
          @click="emit('cancel')"
        >
          <template #icon>
            <n-icon :component="StopOutline" />
          </template>
        </n-button>
        <n-button
          v-else
          type="primary"
          round
          :disabled="!input.trim()"
          @click="send"
        >
          <template #icon>
            <n-icon :component="SendOutline" />
          </template>
        </n-button>
      </div>

      <!-- 微型 Toggle 行：RAG 检索 / 自一致性评估 + 免责提示小字 -->
      <div
        class="flex items-center justify-between border-t border-slate-100 px-3 pb-2 pt-1.5 dark:border-slate-700"
      >
        <div class="flex items-center gap-4">
          <label class="flex cursor-pointer select-none items-center gap-1.5 text-[11px] text-slate-500 dark:text-slate-400">
            <n-switch v-model:value="settings.useRag" size="small" />
            RAG 检索
          </label>
          <label class="flex cursor-pointer select-none items-center gap-1.5 text-[11px] text-slate-500 dark:text-slate-400">
            <n-switch v-model:value="settings.enableConsistency" size="small" />
            自一致性评估
          </label>
        </div>
        <span class="hidden text-[11px] text-slate-400 sm:inline">
          回答由 AI 生成，仅供参考
        </span>
      </div>
    </div>
  </div>
</template>
