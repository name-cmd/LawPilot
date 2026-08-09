<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { NButton, NIcon, NSwitch, useMessage } from 'naive-ui'
import { AttachOutline, DocumentTextOutline, SendOutline, StopOutline } from '@vicons/ionicons5'
import ModelSelector from '@/components/chat/ModelSelector.vue'
import { useSessionsStore } from '@/stores/sessions'
import { useSettingsStore } from '@/stores/settings'
import { uploadDocument } from '@/api/misc'
import { isApiError } from '@/api/client'
import type { PendingAttachment } from '@/stores/sessions'

const settings = useSettingsStore()
const sessions = useSessionsStore()
const toast = useMessage()

/** 与后端一致：最多 5 个附件 */
const MAX_ATTACHMENTS = 5

const input = ref('')
const textareaRef = ref<HTMLTextAreaElement | null>(null)
/** 隐藏的文件选择框（accept 与后端 DocumentExtractor 支持的格式对齐） */
const fileInputRef = ref<HTMLInputElement | null>(null)

const props = defineProps<{
  /** 是否有问答请求进行中：true 时发送按钮变为「停止」 */
  streaming?: boolean
  /** 当前会话是否有可导出的法律问答（无可导出时隐藏「导出报告」入口） */
  canExport?: boolean
}>()

const emit = defineEmits<{ send: []; cancel: []; 'export-mode': [] }>()

// ── 文档上传（旧版 uploadDocument 语义：占位 → 解析 → 更新；失败移除并提示） ──
function onPickFiles(e: Event) {
  const files = Array.from((e.target as HTMLInputElement).files || [])
  ;(e.target as HTMLInputElement).value = ''
  files.forEach((f) => upload(f))
}

async function upload(file: File) {
  if (sessions.pendingAttachments.length >= MAX_ATTACHMENTS) {
    toast.warning(`最多上传 ${MAX_ATTACHMENTS} 个文档`)
    return
  }
  const placeholder: PendingAttachment = {
    filename: file.name,
    uploading: true,
    char_count: 0,
    text: '',
    format: '',
  }
  sessions.pendingAttachments.push(placeholder)
  try {
    const data = await uploadDocument(file)
    // 按占位对象引用定位（并发上传多个文件时索引会漂移，用文件名查会误命中同名文件）
    const idx = sessions.pendingAttachments.indexOf(placeholder)
    if (idx >= 0) {
      sessions.pendingAttachments[idx] = {
        filename: data.filename,
        text: data.text,
        format: data.format,
        char_count: data.char_count,
        uploading: false,
      }
    }
    if (data.warnings?.length) toast.info(data.warnings.join('；'))
  } catch (e) {
    const idx = sessions.pendingAttachments.indexOf(placeholder)
    if (idx >= 0) sessions.pendingAttachments.splice(idx, 1)
    toast.error(isApiError(e) ? e.message : String(e))
  }
}

function removeAttachment(idx: number) {
  sessions.pendingAttachments.splice(idx, 1)
}

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
  <div class="px-4 pb-3 pt-2">
    <div
      class="w-full overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-lg transition-shadow focus-within:border-blue-400 focus-within:shadow-xl dark:border-slate-700 dark:bg-slate-800"
    >
      <!-- 输入行：仅文本域（模型选择器与发送按钮在下方右下角，参考 DeepSeek 布局） -->
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
      </div>

      <!-- 待发送附件列表（上传解析中 / 已完成），旧版 attachment-list 语义 -->
      <div v-if="sessions.pendingAttachments.length" class="flex flex-wrap gap-1.5 px-3 pt-1.5">
        <span
          v-for="(a, i) in sessions.pendingAttachments"
          :key="`${a.filename}-${i}`"
          class="inline-flex items-center gap-1.5 rounded-full bg-slate-100 py-0.5 pl-2 pr-1 text-[11px] text-slate-600 dark:bg-slate-700 dark:text-slate-300"
        >
          <span class="max-w-36 truncate" :title="a.filename">{{ a.filename }}</span>
          <span class="text-slate-400 dark:text-slate-500">
            {{ a.uploading ? '解析中…' : `${a.char_count} 字` }}
          </span>
          <button
            type="button"
            class="rounded-full px-1 leading-none hover:bg-slate-200 hover:text-slate-800 dark:hover:bg-slate-600 dark:hover:text-slate-100"
            title="移除附件"
            @click="removeAttachment(i)"
          >
            ×
          </button>
        </span>
      </div>

      <!-- 底部行：左侧功能开关，右侧模型选择器 + 发送/停止按钮 -->
      <div
        class="flex items-center justify-between border-t border-slate-100 px-3 py-1.5 dark:border-slate-700"
      >
        <div class="flex items-center gap-4">
          <!-- 上传按钮：隐藏 file input 触发选择（accept 与后端支持格式对齐） -->
          <input
            ref="fileInputRef"
            type="file"
            multiple
            accept=".txt,.md,.docx,.pdf,.jpg,.jpeg,.png,.bmp,.tiff,.webp"
            class="hidden"
            @change="onPickFiles"
          />
          <button
            type="button"
            class="flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-[11px] text-slate-500 transition-colors hover:bg-slate-100 hover:text-brand-500 dark:text-slate-400 dark:hover:bg-slate-700"
            title="上传 txt / Word / PDF / 图片（最多 5 个，每个 ≤10MB）"
            @click="fileInputRef?.click()"
          >
            <n-icon :component="AttachOutline" size="16" />
            上传文件
          </button>
          <!-- 导出报告入口：进入导出模式勾选法律问答（legacy 导出模式按钮语义） -->
          <button
            v-if="canExport !== false"
            type="button"
            class="flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-[11px] text-slate-500 transition-colors hover:bg-slate-100 hover:text-brand-500 dark:text-slate-400 dark:hover:bg-slate-700"
            title="勾选对话导出可信评估报告"
            @click="emit('export-mode')"
          >
            <n-icon :component="DocumentTextOutline" size="15" />
            导出报告
          </button>
          <label class="flex cursor-pointer select-none items-center gap-1.5 text-[11px] text-slate-500 dark:text-slate-400">
            <n-switch v-model:value="settings.useRag" size="small" />
            RAG 检索
          </label>
          <label class="flex cursor-pointer select-none items-center gap-1.5 text-[11px] text-slate-500 dark:text-slate-400">
            <n-switch v-model:value="settings.enableConsistency" size="small" />
            自一致性评估
          </label>
        </div>
        <div class="flex items-center gap-1.5">
          <ModelSelector />
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
      </div>
    </div>

    <!-- 免责提示（卡片外底部居中） -->
    <div class="mt-2 text-center text-[11px] text-slate-400 dark:text-slate-500">
      回答由 AI 生成，仅供参考
    </div>
  </div>
</template>
