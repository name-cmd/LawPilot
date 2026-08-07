<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import AppHeader from '@/components/layout/AppHeader.vue'
import SessionSidebar from '@/components/layout/SessionSidebar.vue'
import DetailPanel from '@/components/layout/DetailPanel.vue'
import ChatInput from '@/components/chat/ChatInput.vue'
import ChatMessage from '@/components/chat/ChatMessage.vue'
import PrivacyConfirmModal from '@/components/chat/PrivacyConfirmModal.vue'
import { useSessionsStore } from '@/stores/sessions'
import { useModelsStore } from '@/stores/models'
import { useDetailPanelStore } from '@/stores/detailPanel'
import { useChatStream, isAbortError } from '@/composables/useChatStream'
import { useVerificationWS } from '@/composables/useVerificationWS'
import { checkInput } from '@/api/misc'
import { isApiError } from '@/api/client'
import { uid } from '@/utils/id'
import { isLegalAnalysisMeta } from '@/utils/answer'

const sessions = useSessionsStore()
const models = useModelsStore()
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
watch(
  () => sessions.currentSession?.messages.map((m) => m.content).join('|'),
  () => scrollToBottom(),
)

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
  if (!rawQuery) {
    toast.warning('请输入法律问题')
    return
  }
  const confirmed = privacyConfirmed === true
  const queryForCheck = rawQuery

  const session = sessions.currentSession
  if (!session) {
    toast.error('会话未就绪，请刷新页面或新建会话')
    return
  }

  // 1. 先占位（用户消息 + 助手思考气泡），再走输入守卫
  const { userMsg, assistantMsg } = sessions.addQuestionMessages(rawQuery, [])
  sessions.autoTitle(session.id, rawQuery)
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
    inputRef?.setInput(check.critical_pii_masked ? query : rawQuery)
    privacyMessage.value = check.privacy_warning || '您的问题包含疑似个人信息，请确认是否继续发送。'
    privacyShow.value = true
    return
  }

  await runChatPipeline(query, userMsg.id, assistantMsg.id, confirmed || !check.needs_privacy_confirm)
}

/** 流式问答 + 自动降级 + 错误回滚（旧版 runChatPipeline 语义） */
async function runChatPipeline(query: string, userMsgId: string, assistantMsgId: string, privacyConfirmed: boolean) {
  sessions.loading = true
  sessions.updateMessage(assistantMsgId, { thinkingText: '正在准备分析…' })
  scrollToBottom()

  const payload = sessions.buildChatPayload(query, assistantMsgId, privacyConfirmed)
  let metaReceived = false

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
              model_id: meta.model_id,
              model_name: meta.model_name,
            },
          })
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
              model_id: done.model_id ?? m?.meta?.model_id,
              model_name: done.model_name ?? m?.meta?.model_name,
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
              model_id: done.model_id ?? meta.model_id,
              model_name: done.model_name ?? meta.model_name,
            }
            // 法律类回答：自动在右侧面板展示可信评估（追问时自动切到最新回答）
            detail.autoShow(assistantMsgId)
          }
          sessions.updateMessage(assistantMsgId, patch as never)
          // 法律类回答：连接核验 WebSocket，等待后台完整核验结果
          if (!done.non_legal && metaReceived) {
            verification.connect(assistantMsgId, {
              onComplete: (data) => {
                const m = sessions.currentSession?.messages.find((x) => x.id === assistantMsgId)
                const meta = m?.meta || {}
                sessions.updateMessage(assistantMsgId, {
                  meta: {
                    ...meta,
                    citation_verification: data.citation_verification,
                    consistency: data.consistency,
                    trust: data.trust,
                    validity_warnings: data.validity_warnings || [],
                    verification_status: 'complete',
                    regeneration_attempts: data.regeneration_attempts || 0,
                  },
                })
              },
              onError: (err) => {
                // 核验失败防呆：置为 error 退出"核验中"状态，面板展示已有初步评估
                // （否则详情永远显示"核验中 · 初步回答已生成"，用户以为卡死）
                const m = sessions.currentSession?.messages.find((x) => x.id === assistantMsgId)
                if (m) {
                  sessions.updateMessage(assistantMsgId, {
                    meta: { ...(m.meta || {}), verification_status: 'error' },
                  })
                }
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
              model_id: data.model_id as string | undefined,
              model_name: data.model_name as string | undefined,
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
            />
          </div>
        </div>

        <!-- 输入区 -->
        <ChatInput
          ref="chatInputRef"
          :streaming="sessions.loading"
          @send="ask()"
          @cancel="cancel()"
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
