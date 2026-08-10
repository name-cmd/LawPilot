/**
 * 服务端双写同步（改进指南阶段三 3.3）。
 *
 * 策略：
 * - pull()：登录后拉取服务端会话/收藏；
 *   服务端已有数据（exists=true）→ 以服务端为准覆盖本地（换设备/清缓存后恢复）；
 *   服务端无数据（exists=false，首次登录该账号）→ 本地数据回写服务端（老用户迁移）。
 * - 会话/收藏变化 → 3 秒防抖整包提交服务端；失败静默（下次变更再试），不阻塞界面。
 * - 服务端不可达 → localStorage 照常使用（降级不中断）。
 */
import { watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useSessionsStore } from '@/stores/sessions'
import { useFavoritesStore } from '@/stores/favorites'
import { fetchUserData, saveUserData } from '@/api/user'

const PUSH_DEBOUNCE_MS = 3000

export function useSync() {
  // 单例：App.vue / 登录页 / 路由守卫都会调用 useSync，但 watcher 只允许存在一份，
  // 否则同一次数据变化会被多个防抖计时器重复推送
  if (!_instance) _instance = createSync()
  return _instance
}

let _instance: ReturnType<typeof createSync> | null = null

function createSync() {
  const auth = useAuthStore()
  const sessions = useSessionsStore()
  const favorites = useFavoritesStore()

  let timer: ReturnType<typeof setTimeout> | null = null

  /** 登录后调用：从服务端恢复数据（换设备/清缓存后回填）；首次登录则回写本地数据 */
  async function pull() {
    if (!auth.token) return
    try {
      const data = await fetchUserData(auth.token)
      if (data.exists) {
        // 服务端有数据 → 以服务端为准（回写 localStorage 由 persist 插件自动完成）
        sessions.$patch({ sessions: data.sessions })
        sessions.ensureSession()
        favorites.$patch({ favorites: data.favorites })
      } else {
        // 首次登录该账号：把本地既有数据回写服务端（老用户迁移，不丢历史）
        pushNow()
      }
    } catch {
      /* 服务端不可达：降级用本地数据，不中断 */
    }
  }

  /** 立即整包提交（无防抖；拉取回写与登出前的兜底用） */
  function pushNow() {
    if (!auth.token) return
    saveUserData(auth.token, sessions.sessions, favorites.favorites).catch(() => {
      /* 提交失败静默，下次变更再试 */
    })
  }

  /** 防抖提交：会话/收藏变化后 3 秒内多次变更只提交一次 */
  function schedulePush() {
    if (!auth.token) return
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      timer = null
      pushNow()
    }, PUSH_DEBOUNCE_MS)
  }

  // 深度监听会话与收藏（新增消息/收藏/清空都会触发），登录状态下防抖提交
  watch([() => sessions.sessions, () => favorites.favorites], schedulePush, { deep: true })

  return { pull, pushNow }
}

