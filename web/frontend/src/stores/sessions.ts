import { defineStore } from 'pinia'
import { useAuthStore } from './auth'
import { useSettingsStore } from './settings'
import { autoTitle } from '@/api/misc'
import { sessionId, uid } from '@/utils/id'
import { SESSIONS_PREFIX_V2, SESSIONS_PREFIX_V1, migrateJson, userScopedStorage } from '@/utils/storage'
import type { HistoryItem, MessageMeta } from '@/api/types'

// ── 数据结构（与旧版 localStorage 格式一致，迁移零转换） ──
export interface MessageAttachment {
  filename: string
  char_count: number
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

    /** 登录后加载该用户的会话：v1 迁移 + hydrate + 兜底建会话 */
    async loadForCurrentUser() {
      const auth = useAuthStore()
      if (auth.username) {
        migrateJson(`${SESSIONS_PREFIX_V1}${auth.username}`, this.storageKeyV2())
      }
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

    updateMessage(id: string, patch: Partial<Message>) {
      const m = this.currentSession?.messages.find((x) => x.id === id)
      if (m) Object.assign(m, patch)
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
