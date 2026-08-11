import { defineStore } from 'pinia'
import { useAuthStore } from './auth'
import { useSettingsStore } from './settings'
import { autoTitle } from '@/api/misc'
import { sessionId, uid } from '@/utils/id'
import { SESSIONS_PREFIX_V2, SESSIONS_PREFIX_V1, migrateJson, userScopedStorage } from '@/utils/storage'
import type { HistoryItem, MessageMeta, VerificationComplete } from '@/api/types'

// ── 数据结构（与旧版 localStorage 格式一致，迁移零转换） ──
export interface MessageAttachment {
  filename: string
  char_count: number
  /** 文档文本（截断至后端 DOC_MAX_CONTEXT_CHARS 上限后保存）：重新生成回答时
      附件队列已清空，靠它把文档上下文带回给模型 */
  text?: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  attachments?: MessageAttachment[]
  meta?: MessageMeta
  feedback?: { rating: 'up' | 'down'; reason?: string }
  refusal?: boolean
  loading?: boolean
  thinkingText?: string
  timestamp: number
}

export interface Session {
  id: string
  title: string
  titleManual: boolean
  createdAt: number
  updatedAt: number
  messages: Message[]
}

/** 待发送附件（上传解析中/已完成） */
export interface PendingAttachment {
  filename: string
  uploading: boolean
  char_count: number
  text: string
  format: string
}

export const useSessionsStore = defineStore('sessions', {
  state: () => ({
    sessions: [] as Session[],
    currentSessionId: null as string | null,
    pendingAttachments: [] as PendingAttachment[],
    /** 是否有问答请求在进行中（发送按钮/输入框状态） */
    loading: false,
  }),

  getters: {
    currentSession: (s) => s.sessions.find((x) => x.id === s.currentSessionId) ?? null,
  },

  actions: {
    /** 会话列表 key（按用户名隔离，与旧版逻辑一致） */
    storageKeyV2() {
      const auth = useAuthStore()
      return `${SESSIONS_PREFIX_V2}${auth.username || 'guest'}`
    },

    /** 登录后加载该用户的会话：v1 迁移 + 清空旧账号内存数据 + hydrate + 兜底建会话 */
    async loadForCurrentUser() {
      const auth = useAuthStore()
      if (auth.username) {
        migrateJson(`${SESSIONS_PREFIX_V1}${auth.username}`, this.storageKeyV2())
      }
      // 先重置再 hydrate：切换账号时若新账号本地没有数据（localStorage 无该 key），
      // persist 插件的 hydrate 不会改动 state，残留的上一个账号会话会留在内存里，
      // 随后 pull() 的「首次登录回写」会把残留数据误传到新账号（跨账号串数据）。
      this.$reset()
      this.$hydrate()
      this.ensureSession()
    },

    /** 会话不存在或当前 id 失效时兜底（旧版 loadSessions 语义） */
    ensureSession() {
      // 旧数据可能缺少 titleManual 字段，补默认值（先展开再补，避免对象字面量重复键）
      this.sessions = this.sessions.map((s) => ({
        ...s,
        titleManual: Boolean(s.titleManual),
      }))
      if (!this.sessions.length) {
        this.createSession(false)
      }
      if (!this.currentSessionId || !this.sessions.find((s) => s.id === this.currentSessionId)) {
        this.currentSessionId = this.sessions[0]?.id ?? null
      }
    },

    createSession(switchTo = true): Session {
      const s: Session = {
        id: sessionId(),
        title: '新对话',
        titleManual: false,
        createdAt: Date.now(),
        updatedAt: Date.now(),
        messages: [],
      }
      this.sessions.unshift(s)
      if (switchTo || !this.currentSessionId) this.currentSessionId = s.id
      return s
    },

    switchSession(id: string) {
      if (this.sessions.find((s) => s.id === id)) this.currentSessionId = id
    },

    deleteSession(id: string) {
      this.sessions = this.sessions.filter((s) => s.id !== id)
      if (!this.sessions.length) this.createSession(true)
      else if (this.currentSessionId === id) this.currentSessionId = this.sessions[0].id
    },

    clearAllSessions() {
      this.sessions = []
      this.createSession(true)
    },

    renameSession(id: string, title: string) {
      const s = this.sessions.find((x) => x.id === id)
      if (!s) return
      s.title = title.trim() || s.title
      s.titleManual = true
    },

    appendMessage(msg: Message) {
      this.currentSession?.messages.push(msg)
    },

    /**
     * 更新消息（跨会话查找）：消息 id 全局唯一，核验结果经 WS 异步到达时用户可能已
     * 切到别的会话——若只查当前会话会找不到消息而丢弃结果，消息永远停在「核验中」。
     * （已在后端日志确认：广播成功但前端不应用，切会话场景必现）
     */
    updateMessage(id: string, patch: Partial<Message>) {
      for (const s of this.sessions) {
        const m = s.messages.find((x) => x.id === id)
        if (m) {
          Object.assign(m, patch)
          return
        }
      }
    },

    /**
     * 应用核验结果（WS 广播 / 详情面板自愈重连共用）：跨会话查找消息并合并核验数据。
     * 与 updateMessage 同样的跨会话语义——核验完成时用户可能在别的会话浏览。
     */
    applyVerificationResult(messageId: string, data: VerificationComplete) {
      for (const s of this.sessions) {
        const m = s.messages.find((x) => x.id === messageId)
        if (m) {
          m.meta = {
            ...(m.meta || {}),
            citation_verification: data.citation_verification,
            consistency: data.consistency,
            trust: data.trust,
            validity_warnings: data.validity_warnings || [],
            verification_status: 'complete',
            regeneration_attempts: data.regeneration_attempts || 0,
          }
          return
        }
      }
    },

    /** 核验失败防呆：跨会话置为 error，退出「核验中」状态（面板展示已有初步评估） */
    applyVerificationError(messageId: string) {
      for (const s of this.sessions) {
        const m = s.messages.find((x) => x.id === messageId)
        if (m) {
          m.meta = { ...(m.meta || {}), verification_status: 'error' }
          return
        }
      }
    },

    removeMessages(ids: string[]) {
      const session = this.currentSession
      if (!session) return
      const set = new Set(ids)
      session.messages = session.messages.filter((m) => !set.has(m.id))
    },

    /**
     * 自动标题：首条提问后调用 /api/session-title，失败退回截断标题（旧版语义）。
     * 手动改过标题后不再覆盖。
     */
    async autoTitle(sessionId: string, firstUserText: string) {
      const touch = () => {
        const s = this.sessions.find((x) => x.id === sessionId)
        if (s) s.updatedAt = Date.now()
      }
      touch()
      const s = this.sessions.find((x) => x.id === sessionId)
      if (!s || s.titleManual || !firstUserText) return
      try {
        const data = await autoTitle(firstUserText)
        const cur = this.sessions.find((x) => x.id === sessionId)
        if (cur && !cur.titleManual && data.title) {
          cur.title = data.title
          cur.updatedAt = Date.now()
        }
      } catch {
        const cur = this.sessions.find((x) => x.id === sessionId)
        if (cur && !cur.titleManual) {
          cur.title =
            firstUserText.slice(0, 18) + (firstUserText.length > 18 ? '…' : '')
          cur.updatedAt = Date.now()
        }
      }
    },

    /**
     * 构造发给后端的 history。
     * 旧版语义：传 session.messages.slice(0, -2)（去掉刚追加的 user+assistant 两条），
     * 再过滤掉 loading 中的消息，只保留 user/assistant 的 content。
     */
    buildHistoryForApi(messages: Message[]): HistoryItem[] {
      return messages
        .filter((m) => !m.loading && (m.role === 'user' || m.role === 'assistant'))
        .map((m) => ({ role: m.role, content: m.content }))
    },

    /** 生成本次问答的请求体（含 message_id，流式与核验任务共用） */
    buildChatPayload(query: string, messageId: string, privacyConfirmed: boolean) {
      const session = this.currentSession
      const settings = useSettingsStore()
      return {
        query,
        message_id: messageId,
        history: session ? this.buildHistoryForApi(session.messages.slice(0, -2)) : [],
        use_rag: settings.useRag,
        enable_consistency: settings.enableConsistency,
        enable_nli: settings.enableNli,
        n_consistency_samples: settings.nConsistencySamples,
        privacy_confirmed: privacyConfirmed,
        // 模型选择：离线调用传 'local'，API 调用传选择器里的 'auto' 或具体模型 id
        model: settings.modelProvider === 'local' ? 'local' : settings.apiModel,
        // 设置面板的全局默认模型（Auto 跟随；后端解析为准）
        global_model: settings.globalDefaultModel,
        // 登录 Token：后端凭它解析该账号自配的 API Key（未登录不发）
        token: useAuthStore().token || undefined,
        user_documents: this.pendingAttachments
          .filter((a) => !a.uploading && a.text)
          .map((a) => ({
            filename: a.filename,
            text: a.text,
            format: a.format,
            char_count: a.char_count,
          })),
      }
    },

    /** 新建提问消息（用户+助手占位） */
    addQuestionMessages(displayQuery: string, attachments: MessageAttachment[]) {
      const userMsg: Message = {
        id: uid(),
        role: 'user',
        content: displayQuery,
        attachments,
        timestamp: Date.now(),
      }
      const assistantMsg: Message = {
        id: uid(),
        role: 'assistant',
        content: '',
        loading: true,
        thinkingText: '正在理解您的问题…',
        timestamp: Date.now(),
      }
      this.appendMessage(userMsg)
      this.appendMessage(assistantMsg)
      return { userMsg, assistantMsg }
    },
  },
  persist: {
    key: 'lawtrust_sessions_v2',
    storage: userScopedStorage(),
  },
})
