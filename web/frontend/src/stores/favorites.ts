import { defineStore } from 'pinia'
import { useAuthStore } from './auth'
import { useSessionsStore } from './sessions'
import { FAVORITES_PREFIX_V1, FAVORITES_PREFIX_V2, migrateJson, userScopedStorage } from '@/utils/storage'
import type { MessageMeta } from '@/api/types'

/** 收藏条目（结构与旧版 lawtrust_favorites_v1 完全一致，迁移零转换） */
export interface Favorite {
  id: string
  messageId: string
  sessionId: string
  title: string
  note: string
  query: string
  content: string
  meta: MessageMeta
  createdAt: number
  updatedAt: number
}

export const useFavoritesStore = defineStore('favorites', {
  state: () => ({
    favorites: [] as Favorite[],
  }),

  getters: {
    isFavorited: (s) => (messageId: string) => s.favorites.some((f) => f.messageId === messageId),
  },

  actions: {
    /** 存储 key（按用户名隔离） */
    storageKeyV2() {
      const auth = useAuthStore()
      return `${FAVORITES_PREFIX_V2}${auth.username || 'guest'}`
    },

    /** 登录后加载该用户收藏：v1 迁移 + hydrate（与 sessions 同模式） */
    loadForCurrentUser() {
      const auth = useAuthStore()
      if (auth.username) {
        migrateJson(`${FAVORITES_PREFIX_V1}${auth.username}`, this.storageKeyV2())
      }
      this.$hydrate()
    },

    /** 收藏/取消收藏一条 AI 回答（数据快照进收藏，跨会话可看） */
    toggleFavorite(messageId: string) {
      const sessions = useSessionsStore()
      const msg = sessions.sessions.flatMap((s) => s.messages).find((m) => m.id === messageId)
      if (!msg) return 'none'

      const existing = this.favorites.find((f) => f.messageId === messageId)
      if (existing) {
        this.favorites = this.favorites.filter((f) => f.messageId !== messageId)
        return 'removed'
      }

      // 找配对的上一条用户消息作为标题（旧版 getPairedUserMessage 语义）
      const session = sessions.sessions.find((s) => s.id === sessions.currentSessionId)
      const allMessages = session?.messages || []
      const idx = allMessages.findIndex((m) => m.id === messageId)
      const userMsg = idx > 0 && allMessages[idx - 1].role === 'user' ? allMessages[idx - 1] : null

      this.favorites.unshift({
        id: `fav_${Date.now()}_${Math.floor(Math.random() * 10000)}`,
        messageId,
        sessionId: sessions.currentSessionId || '',
        title: (userMsg?.content || '法律问答').slice(0, 40),
        note: '',
        query: userMsg?.content || '',
        content: msg.content,
        meta: JSON.parse(JSON.stringify(msg.meta || {})),
        createdAt: Date.now(),
        updatedAt: Date.now(),
      })
      return 'added'
    },

    updateFavorite(id: string, title: string, note: string) {
      const f = this.favorites.find((x) => x.id === id)
      if (!f) return
      f.title = title.trim() || f.title
      f.note = note.trim()
      f.updatedAt = Date.now()
    },

    removeFavorite(id: string) {
      this.favorites = this.favorites.filter((f) => f.id !== id)
    },
  },
  persist: {
    key: FAVORITES_PREFIX_V2,
    storage: userScopedStorage(),
  },
})
