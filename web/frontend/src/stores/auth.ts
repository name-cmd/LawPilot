import { defineStore } from 'pinia'
import { AUTH_KEY_V1, AUTH_KEY_V2, PROFILE_PREFIX_V1, migrateJson } from '@/utils/storage'
import { login as apiLogin, logout as apiLogout, verifyToken } from '@/api/auth'
import type { LoginResponse } from '@/api/types'

export interface UserProfile {
  username: string
  displayName: string
  bio: string
  avatarColor: string
  avatarData: string | null
}

/**
 * 登录态 + 个人资料。
 * 持久化 key：lawtrust_auth_v2（旧版 v1 数据在 main.ts 启动时已静默迁移）。
 */
export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: null as string | null,
    username: null as string | null,
    displayName: null as string | null,
    profile: null as UserProfile | null,
  }),
  getters: {
    isLoggedIn: (s) => Boolean(s.token),
    /** 昵称或用户名（用户菜单/头像显示用） */
    displayLabel: (s) => s.profile?.displayName || s.displayName || s.username || '',
  },
  actions: {
    /** 登录成功后写入登录态（token/username/displayName 持久化，刷新保持） */
    setSession(data: LoginResponse) {
      this.token = data.token
      this.username = data.username
      this.displayName = data.display_name || data.username
    },

    /** 启动时恢复会话：先做 v1→v2 迁移，再向后端校验 token 有效性 */
    async restoreSession(): Promise<boolean> {
      // 旧版登录态迁移（v1 → v2，persist 插件在 store 实例化时读取 v2）
      migrateJson(AUTH_KEY_V1, AUTH_KEY_V2)

      if (!this.token || !this.username) return false
      // 旧版个人资料迁移（key 按用户名后缀，M4 资料页完整化前先带入）
      if (!this.profile) this.loadProfileV1()
      // 服务不可达时退回本地登录态（与旧版一致）
      try {
        const res = await verifyToken(this.token)
        if (res.valid) {
          this.displayName = res.display_name || this.username
          return true
        }
        return false
      } catch {
        return Boolean(this.token && this.username)
      }
    },

    async login(username: string, password: string) {
      const data = await apiLogin(username, password)
      this.setSession(data)
      this.loadProfileV1()
    },

    /** 从旧版 lawtrust_profile_v1_{username} 读取个人资料（v1 迁移源） */
    loadProfileV1() {
      if (!this.username) return
      try {
        const raw = localStorage.getItem(`${PROFILE_PREFIX_V1}${this.username}`)
        if (raw) this.profile = JSON.parse(raw)
      } catch {
        /* 忽略损坏的旧数据 */
      }
    },

    /** 保存个人资料（写入 auth state，persist 插件自动持久化到 lawtrust_auth_v2） */
    updateProfile(patch: Partial<Omit<UserProfile, 'username'>>) {
      const base = this.profile || { username: this.username || '', displayName: '', bio: '', avatarColor: '', avatarData: null }
      this.profile = { ...base, username: this.username || base.username, ...patch }
    },

    async logout() {
      if (this.token) {
        try {
          await apiLogout(this.token)
        } catch {
          /* 忽略登出请求失败，照旧版行为 */
        }
      }
      this.$reset()
    },
  },
  persist: { key: AUTH_KEY_V2 },
})
