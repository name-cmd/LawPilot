/**
 * localStorage 兼容层：旧版（v1）key 定义与静默迁移。
 * 迁移策略：新 key 不存在且旧 key 存在 → 原样搬入（不删旧 key，留作回退）。
 */
import { useAuthStore } from '@/stores/auth'

export const AUTH_KEY_V2 = 'lawtrust_auth_v2'
export const AUTH_KEY_V1 = 'lawtrust_auth_v1'
export const SETTINGS_KEY = 'lawtrust_settings_v1'

export const SESSIONS_PREFIX_V2 = 'lawtrust_sessions_v2_'
export const SESSIONS_PREFIX_V1 = 'lawtrust_sessions_v1_'

export const FAVORITES_PREFIX_V2 = 'lawtrust_favorites_v2_'
export const FAVORITES_PREFIX_V1 = 'lawtrust_favorites_v1_'

export const PROFILE_PREFIX_V1 = 'lawtrust_profile_v1_'

/** 通用迁移：把 oldKey 的内容搬到 newKey（新 key 已存在或旧 key 缺失则不动）。 */
export function migrateJson(oldKey: string, newKey: string): boolean {
  if (localStorage.getItem(newKey) !== null) return false
  const raw = localStorage.getItem(oldKey)
  if (!raw) return false
  localStorage.setItem(newKey, raw)
  return true
}

/** 迁移登录态：lawtrust_auth_v1 → lawtrust_auth_v2（须在 auth store 实例化前调用） */
export function migrateAuthV1(): void {
  migrateJson(AUTH_KEY_V1, AUTH_KEY_V2)
}

/**
 * 按用户隔离的 storage：实际 key = 配置 key + 用户名后缀（与旧版逻辑一致）。
 * 插件只会在 store 创建时求值一次 key，因此动态用户名必须在 getItem/setItem
 * 每次调用时解析（登录/切换用户后 $hydrate/$persist 自动落到正确的 key）。
 * sessions / favorites 等按用户隔离的 store 共用。
 */
export function userScopedStorage() {
  const resolveKey = (key: string) => {
    const auth = useAuthStore()
    return `${key}_${auth.username || 'guest'}`
  }
  return {
    getItem: (key: string) => localStorage.getItem(resolveKey(key)),
    setItem: (key: string, value: string) => localStorage.setItem(resolveKey(key), value),
  }
}
