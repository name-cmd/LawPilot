<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import AppHeader from '@/components/layout/AppHeader.vue'
import SessionSidebar from '@/components/layout/SessionSidebar.vue'
import DetailPanel from '@/components/layout/DetailPanel.vue'
import ChatInput from '@/components/chat/ChatInput.vue'
import ChatMessage from '@/components/chat/ChatMessage.vue'
import ExportBar from '@/components/chat/ExportBar.vue'
import PrivacyConfirmModal from '@/components/chat/PrivacyConfirmModal.vue'
import { exportTrustReport, getExportableMessages } from '@/utils/report'
import { useSessionsStore } from '@/stores/sessions'
import { useModelsStore } from '@/stores/models'
import { useSettingsStore } from '@/stores/settings'
import { useDetailPanelStore } from '@/stores/detailPanel'
import { useChatStream, isAbortError } from '@/composables/useChatStream'
import { useVerificationWS } from '@/composables/useVerificationWS'
import { checkInput } from '@/api/misc'
import { isApiError } from '@/api/client'
import { uid } from '@/utils/id'
import { isLegalAnalysisMeta } from '@/utils/answer'
import type { Message, MessageAttachment, PendingAttachment } from '@/stores/sessions'
import type { UserDocument } from '@/api/types'

const sessions = useSessionsStore()
const models = useModelsStore()
const settings = useSettingsStore()
const detail = useDetailPanelStore()
const toast = useMessage()
const { ask: askStream, cancel } = useChatStream()
const verification = useVerificationWS()

// 消息区滚动到底
const messageListRef = ref<HTMLElement | null>(null)
const scrollToBottom = () => {
  nextTick(() => {
    if (messageListRef.value) messageListRef.value.scrollTop = messageListRef.value.scrollHeight
  })
}

/**
 * 附件文本截断后存入用户消息：与后端 Config.DOC_MAX_CONTEXT_CHARS（12000 字符）
 * 对齐——后端只会用前 12000 字符，保存更多是浪费 localStorage；
 * 重新生成时把截断后的文本回传，与首次发送的文档上下文一致。
 */
function truncateAttachmentTexts(docs: PendingAttachment[]): MessageAttachment[] {
  const MAX_DOC_CHARS = 12000
  let total = 0
  const out: MessageAttachment[] = []
  for (const d of docs) {
    const text = (d.text || '').trim()
    if (!text) continue
    const remaining = MAX_DOC_CHARS - total
    if (remaining <= 0) break
    out.push({
      filename: d.filename,
      char_count: d.char_count,
      text: text.length > remaining ? text.slice(0, remaining) + '\n…（文档内容已截断）' : text,
    })
    total += Math.min(text.length, remaining)
  }
  return out
}
watch(
  () => sessions.currentSession?.messages.map((m) => m.content).join('|'),
  () => scrollToBottom(),
)

// 切换会话：右侧详情面板同步显示新会话最新一条法律回答的核验详情
// （selectedMsgId 还指着旧会话消息时面板会残留旧内容；新会话无法律回答则清空选择显示空态）
watch(
  () => sessions.currentSessionId,
  () => {
    const msgs = sessions.currentSession?.messages ?? []
    const last = [...msgs]
      .reverse()
      .find((m) => m.role === 'assistant' && !m.loading && isLegalAnalysisMeta(m.meta))
    if (last) detail.autoShow(last.id)
    else detail.clearSelection()
    // 新建/切换会话时退出导出模式（legacy 语义）
    exitExportMode()
  },
)

// ── 导出可信评估报告（功能 36）：导出模式为纯视图状态，放局部 ref 不入 store（避免被持久化） ──
const exportMode = ref(false)
const exportSelected = ref<Set<string>>(new Set())

const exportableMessages = computed(() => getExportableMessages(sessions.currentSession))
const hasLegalMessages = computed(() => exportableMessages.value.length > 0)
const exportAllSelected = computed(
  () => exportableMessages.value.length > 0 && exportableMessages.value.every((m) => exportSelected.value.has(m.id)),
)

function toggleExportMode() {
  if (!hasLegalMessages.value) {
    toast.info('当前对话暂无可导出的法律问答')
    return
  }
  exportMode.value = !exportMode.value
  exportSelected.value = new Set()
}
function exitExportMode() {
  exportMode.value = false
  exportSelected.value = new Set()
}
function toggleExportAll(checked: boolean) {
  if (checked) exportableMessages.value.forEach((m) => exportSelected.value.add(m.id))
  else exportSelected.value.clear()
}
function toggleExportMsg(id: string, checked: boolean) {
  if (checked) exportSelected.value.add(id)
  else exportSelected.value.delete(id)
}
function onExport() {
  const session = sessions.currentSession
  if (!session || exportSelected.value.size === 0) return
  if (exportTrustReport(session, exportSelected.value)) {
    toast.info('报告已生成，请在打印对话框中选择「另存为 PDF」')
    exitExportMode()
  } else {
    toast.warning('请允许弹出窗口以导出报告')
  }
}

// 隐私确认弹窗
const privacyShow = ref(false)
const privacyMessage = ref('')

const chatInputRef = ref<InstanceType<typeof ChatInput> | null>(null)

// 进入页面时：若当前会话有历史法律类回答，自动在右侧详情展示最近一条的评估
// （否则右侧栏显示空态提示，详情栏本身照常显示）
onMounted(() => {
  const msgs = sessions.currentSession?.messages ?? []
  const last = [...msgs]
    .reverse()
    .find((m) => m.role === 'assistant' && !m.loading && isLegalAnalysisMeta(m.meta))
  if (last) detail.autoShow(last.id)
  // 拉取模型目录（模型选择器/设置面板的数据源；失败不阻塞聊天）
  models.fetchModels()
})

/** 追加安全拒答消息（check-input 拒绝时） */
function appendRefusalMessage(query: string, refusalMessage: string) {
  sessions.appendMessage({
    id: uid(),
    role: 'user',
    content: query,
    timestamp: Date.now(),
  })
  sessions.appendMessage({
    id: uid(),
    role: 'assistant',
    content: refusalMessage,
    refusal: true,
    timestamp: Date.now(),
    meta: { refused: true },
  })
  if (sessions.currentSession) {
    sessions.autoTitle(sessions.currentSession.id, query)
  }
}

/** 主流程：提问 → 输入守卫 → （隐私确认）→ 流式问答（失败降级） */
async function ask(privacyConfirmed = false) {
  if (sessions.loading) return
  const inputRef = chatInputRef.value
  const rawQuery = (inputRef?.getInput() || '').trim()
  // 附件：已解析完成的文档（旧版 readyDocs 语义）
  const readyDocs = sessions.pendingAttachments.filter((a) => !a.uploading && a.text)
  if (sessions.pendingAttachments.some((a) => a.uploading)) {
    toast.warning('文档正在解析，请稍候')
    return
  }
  if (!rawQuery && !readyDocs.length) {
    toast.warning('请输入法律问题或上传文档')
    return
  }
  const confirmed = privacyConfirmed === true
  // 仅上传文档不输入文字：自动以文档分析请求作为提问（功能 20 语义）
  const queryForCheck = rawQuery || '请分析以上上传的文档内容，指出关键条款与法律风险。'
  const displayQuery = rawQuery || '（基于上传文档的分析请求）'

  const session = sessions.currentSession
  if (!session) {
    toast.error('会话未就绪，请刷新页面或新建会话')
    return
  }

  // 1. 先占位（用户消息 + 助手思考气泡），再走输入守卫；附件随消息展示（文件名+字数），
  //    文本截断后一并存入（重新生成时回传文档上下文）
  const { userMsg, assistantMsg } = sessions.addQuestionMessages(
    displayQuery,
    truncateAttachmentTexts(readyDocs),
  )
  sessions.autoTitle(session.id, displayQuery)
  inputRef?.clearInput()
  scrollToBottom()

  // 2. 输入守卫检查（隐私/安全拦截）
  let check
  try {
    check = await checkInput(queryForCheck, confirmed)
  } catch (e) {
    sessions.removeMessages([assistantMsg.id, userMsg.id])
    toast.error(isApiError(e) ? e.message : String(e))
    return
  }

  if (check.refused) {
    sessions.removeMessages([assistantMsg.id, userMsg.id])
    appendRefusalMessage(rawQuery, check.refusal_message || '该问题无法回答')
    return
  }

  let query = check.sanitized_query || queryForCheck
  if (rawQuery && query !== rawQuery) {
    sessions.updateMessage(userMsg.id, { content: query })
  }
  if (check.critical_pii_masked) {
    toast.info('已自动脱敏身份证号/银行卡号等极度私密信息')
  }

  // 3. 隐私确认：弹窗征得同意后带 privacy_confirmed=true 重发
  if (check.needs_privacy_confirm && !confirmed) {
    sessions.removeMessages([assistantMsg.id, userMsg.id])
    // 回填 queryForCheck（纯文档提问时 rawQuery 为空，回填空串会丢掉文档分析请求）
    inputRef?.setInput(check.critical_pii_masked ? query : queryForCheck)
    privacyMessage.value = check.privacy_warning || '您的问题包含疑似个人信息，请确认是否继续发送。'
    privacyShow.value = true
    return
  }

  // 4. 发起问答（附件清空移入 runChatPipeline：buildChatPayload 组装 user_documents 之后再清空，
  //    否则 user_documents 恒为空——上一轮修复遗漏的时序 bug；隐私确认未通过时提前 return 不走到这里）
  await runChatPipeline(query, userMsg.id, assistantMsg.id, confirmed || !check.needs_privacy_confirm)
}

/** 流式问答 + 自动降级 + 错误回滚（旧版 runChatPipeline 语义） */
async function runChatPipeline(
  query: string,
  userMsgId: string,
  assistantMsgId: string,
  privacyConfirmed: boolean,
  documents?: UserDocument[],
) {
  sessions.loading = true
  sessions.updateMessage(assistantMsgId, { thinkingText: '正在准备分析…' })
  scrollToBottom()

  const payload = sessions.buildChatPayload(query, assistantMsgId, privacyConfirmed)
  // 附件已组装进 payload.user_documents，随即清空待发送队列（隐私确认重入场景在 ask 中已保留）
  sessions.pendingAttachments = []
  // 重新生成时附件队列已空，文档上下文改从消息附件里保存的截断文本取（覆盖 payload）
  if (documents) payload.user_documents = documents
  let metaReceived = false
  // 发起时选择的模型快照：Auto 模式下左下角显示「Auto」，而非后端解析后的实际模型名
  const requestedModel = settings.apiModel

  try {
    try {
      await askStream(payload, {
        onMeta: (meta) => {
          metaReceived = true
          // 后端首事件必发 meta（含实际使用的模型），法律类并入 RAG 元信息；
          // 模型名在首个 chunk 前就到达，流式中断也不会丢失
          sessions.updateMessage(assistantMsgId, {
            thinkingText: '正在生成回答…',
            meta: {
              intent: meta.intent,
              rag_used: meta.rag_used,
              retrieved_articles: meta.retrieved_articles,
              citation_verification: meta.citation_verification,
              verification_status: 'pending',
              regeneration_attempts: 0,
              requested_model: requestedModel,
              model_id: meta.model_id,
              model_name: meta.model_name,
              // 任务类型优先取顶层字段；后端 Task 8 实际发送的是嵌套 task 对象
              // （task.task_type），双源兼容保证 meta.task_type 一定落盘
              task_type: meta.task_type ?? meta.task?.task_type,
              validity_evidence: meta.validity_evidence,
            },
          })
        },
        onAgentStatus: (s) => {
          const m = sessions.currentSession?.messages.find((x) => x.id === assistantMsgId)
          if (m) m.meta = { ...(m.meta || {}), agent_status: s }
        },
        onToken: (text) => {
          const m = sessions.currentSession?.messages.find((x) => x.id === assistantMsgId)
          if (m) {
            m.content += text
            m.loading = false
            m.thinkingText = undefined
          }
        },
        onDone: (done) => {
          const patch: Record<string, unknown> = { loading: false, thinkingText: undefined }
          if (done.answer) patch.content = done.answer
          if (done.non_legal) {
            // 合并而非覆盖：保留首 meta 事件的模型名（模型信息已在 onMeta 写入 meta）
            const m = sessions.currentSession?.messages.find((x) => x.id === assistantMsgId)
            patch.meta = {
              ...(m?.meta || {}),
              intent: done.intent || { intent: 'greeting' },
              requested_model: requestedModel,
              model_id: done.model_id ?? m?.meta?.model_id,
              model_name: done.model_name ?? m?.meta?.model_name,
              // 非法律回答后端不启动引用核验任务：清除 onMeta 写入的「核验中」
              // 状态，避免气泡永久显示「引用核验中…」
              verification_status: undefined,
              // 流式结束统一清理瞬态 agent_status 并落盘任务元信息
              agent_status: undefined,
              task_type: done.task_type ?? done.task?.task_type,
              validity_evidence: done.validity_evidence,
              tool_trace: done.tool_trace,
            }
            // 寒暄等非法律回答：关闭详情面板，避免旧评估误导
            detail.close()
          } else if (done.trust) {
            const m = sessions.currentSession?.messages.find((x) => x.id === assistantMsgId)
            const meta = m?.meta || {}
            patch.meta = {
              ...meta,
              trust: done.trust,
              verification_status: 'pending',
              requested_model: requestedModel,
              model_id: done.model_id ?? meta.model_id,
              model_name: done.model_name ?? meta.model_name,
              // 流式结束统一清理瞬态 agent_status 并落盘任务元信息
              agent_status: undefined,
              task_type: done.task_type ?? done.task?.task_type,
              validity_evidence: done.validity_evidence,
              tool_trace: done.tool_trace,
            }
            // 法律类回答：自动在右侧面板展示可信评估（追问时自动切到最新回答）
            detail.autoShow(assistantMsgId)
          } else {
            // RAG 未命中或纯文档分析：后端不启动引用核验任务，
            // 清除 onMeta 写入的「核验中」状态，避免消息永久显示「引用核验中…」
            const m = sessions.currentSession?.messages.find((x) => x.id === assistantMsgId)
            patch.meta = {
              ...(m?.meta || {}),
              verification_status: undefined,
              // 流式结束统一清理瞬态 agent_status 并落盘任务元信息
              agent_status: undefined,
              task_type: done.task_type ?? done.task?.task_type,
              validity_evidence: done.validity_evidence,
              tool_trace: done.tool_trace,
            }
          }
          sessions.updateMessage(assistantMsgId, patch as never)
          // 仅 RAG 回答会启动核验后台任务（done.trust 即后端 score_fast 结果），连接 WS 等待完整核验
          if (done.trust && metaReceived) {
            verification.connect(assistantMsgId, {
              // 应用结果走 sessions 跨会话 action：核验期间用户切到别的会话也能正确落盘
              onComplete: (data) => sessions.applyVerificationResult(assistantMsgId, data),
              onError: (err) => {
                // 核验失败防呆：置为 error 退出"核验中"状态，面板展示已有初步评估
                sessions.applyVerificationError(assistantMsgId)
                toast.warning('核验失败：' + err)
              },
            })
          }
        },
        onFallbackStart: () => {
          sessions.updateMessage(assistantMsgId, {
            loading: true,
            content: '',
            thinkingText: '正在重新连接服务…',
          })
        },
        onFallback: (data) => {
          const patch: Record<string, unknown> = { loading: false, thinkingText: undefined }
          if (data.refused) {
            patch.content = data.answer
            patch.refusal = true
            patch.meta = { refused: true }
          } else {
            patch.content = data.answer
            patch.meta = {
              intent: data.intent,
              rag_used: data.rag_used,
              trust: data.trust,
              retrieved_articles: data.retrieved_articles,
              citation_verification: data.citation_verification,
              regeneration_attempts: data.regeneration_attempts || 0,
              verification_status: 'complete',
              requested_model: requestedModel,
              model_id: data.model_id as string | undefined,
              model_name: data.model_name as string | undefined,
              // 同步路径同样清理瞬态 agent_status 并落盘任务元信息
              // （后端 ChatResponse 的 task 为嵌套对象，取 task.task_type）
              agent_status: undefined,
              task_type: (data.task as { task_type?: string } | null | undefined)?.task_type,
              validity_evidence: data.validity_evidence,
              tool_trace: data.tool_trace,
            }
            // 降级回答同样自动展示可信评估
            detail.autoShow(assistantMsgId)
          }
          sessions.updateMessage(assistantMsgId, patch as never)
        },
      })
    } catch (streamErr) {
      // 流式失败（含 abort）统一走外层错误处理
      throw streamErr
    }
  } catch (e) {
    if (isAbortError(e)) {
      // 用户主动取消：保留半截回答，标记完成
      sessions.updateMessage(assistantMsgId, { loading: false, thinkingText: undefined })
      return
    }
    console.warn('[ChatView] 问答失败', e)
    sessions.removeMessages([assistantMsgId])
    const msgs = sessions.currentSession?.messages
    if (msgs && msgs.length && msgs[msgs.length - 1].id === userMsgId) {
      sessions.removeMessages([userMsgId])
      chatInputRef.value?.setInput(query)
    }
    toast.error(isApiError(e) ? e.message : String((e as Error)?.message || e))
  } finally {
    sessions.loading = false
  }
}

/**
 * 重新生成回答（legacy regenerateAnswer 语义）：
 * 移除旧回答 → 追加新占位 → 按原问题重跑流水线。
 * 用户消息保留（历史上下文与附件截断文本都从它取），重答完成后
 * onDone 会自动展示可信评估并连接核验 WS，无需额外处理。
 */
function onRegenerate(assistantMsgId: string) {
  if (sessions.loading) {
    toast.warning('请等待当前回复完成')
    return
  }
  const session = sessions.currentSession
  if (!session) return
  const idx = session.messages.findIndex((m) => m.id === assistantMsgId)
  if (idx < 1) return
  const userMsg = session.messages[idx - 1]
  if (userMsg.role !== 'user') return
  // 移除旧回答，追加新占位（userMsg 保留：历史与附件文本都从它取）
  session.messages.splice(idx, 1)
  const newAssistant: Message = {
    id: uid(),
    role: 'assistant',
    content: '',
    loading: true,
    thinkingText: '正在重新生成回答…',
    timestamp: Date.now(),
  }
  session.messages.push(newAssistant)
  scrollToBottom()
  // 纯文档提问时用户消息显示的是占位文案，重新生成需还原为实际请求
  const query =
    userMsg.content === '（基于上传文档的分析请求）'
      ? '请分析以上上传的文档内容，指出关键条款与法律风险。'
      : userMsg.content
  // 附件文本（截断后保存在消息上）→ user_documents，重新生成不丢文档上下文
  const documents: UserDocument[] = (userMsg.attachments || [])
    .filter((a) => a.text)
    .map((a) => ({
      filename: a.filename,
      text: a.text as string,
      format: '',
      char_count: a.char_count,
    }))
  runChatPipeline(query, userMsg.id, newAssistant.id, true, documents)
}

/** 示例问题点击（欢迎页） */
function onExampleClick(q: string) {
  chatInputRef.value?.setInput(q)
  ask()
}

/** 隐私确认弹窗回调 */
function onPrivacyConfirm() {
  privacyShow.value = false
  ask(true)
}
</script>

<template>
  <!-- h-screen（100vh）：不依赖父级高度。Naive UI 的 provider 包裹层高度为 auto，
       用 h-full 会在中间断链导致布局塌缩成内容高度（界面只占上半屏） -->
  <div class="flex h-screen flex-col">
    <AppHeader />
    <div class="flex min-h-0 flex-1">
      <SessionSidebar />
      <main class="flex min-w-0 flex-1 flex-col bg-slate-100/50 dark:bg-slate-900/60">
        <!-- 导出模式操作栏（消息区上方） -->
        <ExportBar
          v-if="exportMode"
          :selected-count="exportSelected.size"
          :total-count="exportableMessages.length"
          :all-selected="exportAllSelected"
          @toggle-all="toggleExportAll"
          @export="onExport"
          @cancel="exitExportMode"
        />
        <!-- 消息列表 -->
        <div ref="messageListRef" class="flex-1 overflow-y-auto">
          <!-- 消息列表占满聊天区（不设固定最大宽度）：
               收起右侧详情面板后聊天区变宽，消息内容随之自适应变宽 -->
          <div class="space-y-5 px-4 py-6">
            <!-- 空会话欢迎页 -->
            <div v-if="!sessions.currentSession?.messages.length" class="pt-10 text-center">
              <div
                class="mx-auto max-w-xl rounded-xl border border-slate-200 bg-white p-8 shadow-sm dark:border-slate-700 dark:bg-slate-800"
              >
                <div class="mb-3 text-6xl">⚖️</div>
                <h2 class="mb-2 text-xl font-semibold text-slate-900 dark:text-slate-100">开始法律咨询</h2>
                <p class="mb-8 text-sm text-slate-500 dark:text-slate-400">
                  输入问题后可持续追问；法律类回复可查看可信评估、法条溯源与引用核验
                </p>
                <div class="flex flex-wrap justify-center gap-2">
                  <button
                    v-for="q in ['劳动合同解除需要提前多少天通知？', '民间借贷利率的合法上限是多少？', '离婚冷静期是多长时间？']"
                    :key="q"
                    class="rounded-full border border-slate-200 bg-slate-50 px-4 py-2 text-[13px] text-slate-600 transition-colors hover:border-blue-400 hover:text-blue-600"
                    @click="onExampleClick(q)"
                  >
                    {{ q }}
                  </button>
                </div>
              </div>
            </div>

            <!-- 消息列表 -->
            <ChatMessage
              v-for="m in sessions.currentSession?.messages"
              :key="m.id"
              :message="m"
              :export-mode="exportMode"
              :export-checked="exportSelected.has(m.id)"
              @toggle-export="(checked: boolean) => toggleExportMsg(m.id, checked)"
              @regenerate="onRegenerate(m.id)"
            />
          </div>
        </div>

        <!-- 输入区 -->
        <ChatInput
          ref="chatInputRef"
          :streaming="sessions.loading"
          :can-export="hasLegalMessages"
          @send="ask()"
          @cancel="cancel()"
          @export-mode="toggleExportMode"
        />
      </main>
      <DetailPanel />
    </div>

    <!-- 隐私确认 -->
    <PrivacyConfirmModal
      :show="privacyShow"
      :message="privacyMessage"
      @confirm="onPrivacyConfirm"
      @cancel="privacyShow = false"
    />
  </div>
</template>
